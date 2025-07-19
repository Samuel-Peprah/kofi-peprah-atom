import os
import json
from datetime import datetime, timedelta
from flask import Flask, abort, render_template, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import secrets
import socket
import uuid
from PIL import Image
import subprocess
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
from functools import wraps
import requests
import hmac
import hashlib

# Load environment variables from .env file
load_dotenv()

# Import configuration
from config import Config

# Import database and models
from models import db, User, Appointment, UserMessage, Alert, PatientAssessment, Task, client_caregivers, Subscription, Plan

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload and thumbnail folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)

# Initialize extensions with the app
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
mail = Mail(app)
socketio = SocketIO(app, manage_session=False)

PAYSTACK_HEADERS = {"Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}"}


# --- Helper functions for file uploads ---
def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in allowed_extensions

def generate_image_thumbnail(image_path, thumbnail_path, size=(200, 150)):
    try:
        with Image.open(image_path) as img:
            img.thumbnail(size)
            img.save(thumbnail_path)
        return True
    except Exception as e:
        print(f"Error generating image thumbnail for {image_path}: {e}")
        return False

def generate_video_thumbnail(video_path, thumbnail_path, time_offset="00:00:01"):
    """
    Generates a thumbnail from a video using ffmpeg.
    Requires ffmpeg to be installed and available in the system's PATH.
    """
    try:
        # Check if ffmpeg is available
        subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("FFmpeg is not installed or not found in PATH. Video thumbnail generation skipped.")
        return False

    try:
        command = [
            'ffmpeg',
            '-i', video_path,       # Input video file
            '-ss', time_offset,     # Seek to 1 second (or specified offset)
            '-vframes', '1',        # Extract only one frame
            '-s', '320x240',        # Thumbnail size
            '-f', 'image2',         # Output format (image)
            thumbnail_path          # Output thumbnail path
        ]
        subprocess.run(command, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error generating video thumbnail for {video_path}: {e.stderr.decode()}")
        return False
    except Exception as e:
        print(f"Unexpected error during video thumbnail generation for {video_path}: {e}")
        return False

# Output path
output_folder = os.path.join('static', 'images')
os.makedirs(output_folder, exist_ok=True)
output_path = os.path.join(output_folder, 'image_placeholder.png')

# Create a blank image (size: 400x300, color: light blue-ish)
width, height = 400, 300
bg_color = (230, 240, 250)  # Soft light blue
img = Image.new('RGB', (width, height), color=bg_color)
draw = ImageDraw.Draw(img)

# Optional logo path
logo_path = os.path.join('static', 'images', 'gerio_care_logo.png')  # Put your logo here (optional)

# Load and paste logo if it exists
if os.path.exists(logo_path):
    try:
        logo = Image.open(logo_path).convert("RGBA")
        # Resize logo to max 100x100
        logo.thumbnail((100, 100))
        logo_position = ((width - logo.width) // 2, 50)
        img.paste(logo, logo_position, logo)
    except Exception as e:
        print("⚠️ Error loading logo:", e)

# Add text: "No Image Available"
text = "No Image Available"
font_size = 20
try:
    font = ImageFont.truetype("arial.ttf", font_size)
except IOError:
    font = ImageFont.load_default()

bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
text_position = ((width - text_width) // 2, height - text_height - 50)
draw.text(text_position, text, fill=(80, 80, 80), font=font)

# Save the placeholder
img.save(output_path)
print(f"✅ Placeholder saved at: {output_path}")

# # --- Context processor to make 'now' available in all templates ---
# @app.context_processor
# def inject_now():
#     if current_user.is_authenticated:
#         unread_alerts_count = Alert.query.filter_by(user_id=current_user.id, is_read=False).count()
#         return {'now': datetime.utcnow(), 'unread_alerts_count': unread_alerts_count}
#     return {'now': datetime.utcnow(), 'unread_alerts_count': 0}


# NEW: Subscription check function
def has_active_subscription(user):
    """
    Checks if a given user (client) has an active and unexpired subscription.
    Admins, Therapists, and Caregivers do not require subscriptions.
    """
    if not user.is_authenticated or user.role != 'client':
        return True # Non-clients or unauthenticated users don't need a subscription to proceed
    
    # Get the latest active subscription for the client
    latest_subscription = Subscription.query.filter_by(
        user_id=user.id,
        status='active'
    ).order_by(Subscription.expires_at.desc()).first() # Order by expiry to get the latest valid one

    if not latest_subscription:
        return False # No active subscription found

    # Check if the subscription has expired
    return latest_subscription.expires_at > datetime.utcnow()

# MODIFIED: Context processor to inject global data including subscription status
@app.context_processor
def inject_global_data():
    """
    Injects global data into all templates.
    This includes app version, current UTC time, and subscription status.
    """
    has_sub = False
    if current_user.is_authenticated:
        has_sub = has_active_subscription(current_user)

    return {
        'app_version': app.config.get('APP_VERSION', 'N/A'), # Get from config
        'now': datetime.utcnow(), # Using 'now' for consistency with existing templates
        'unread_alerts_count': Alert.query.filter_by(user_id=current_user.id, is_read=False).count() if current_user.is_authenticated else 0,
        'has_active_subscription_func': has_active_subscription, # Make the function itself available
        'user_has_active_subscription': has_sub # A boolean flag for simpler checks in templates
    }

# <--- NEW: Custom Login Required Decorator (replaces Flask-Login's for custom logic)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("You need to be logged in to view this page.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# <--- NEW: Subscription Required Decorator
def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Ensure user is logged in first
        if not current_user.is_authenticated:
            flash("You need to be logged in to view this page.", "info")
            return redirect(url_for("login"))
        
        # Allow admins/therapists/caregivers to bypass subscription checks
        if current_user.role in ['admin', 'therapist', 'caregiver']: # MODIFIED: Added caregiver
            return f(*args, **kwargs)

        # Check for active subscription for clients
        if not has_active_subscription(current_user):
            flash("Please subscribe to a plan to access this feature.", "warning")
            return redirect(url_for("pricing"))
        return f(*args, **kwargs)
    return decorated_function

# <--- NEW: Role Required Decorator
def role_required(*roles):
    """
    Restricts a route to one or more roles.
    Usage: @role_required("admin") or @role_required("therapist", "admin")
    """
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403) # Forbidden
            return fn(*args, **kwargs)
        return decorated
    return wrapper

# --- Flask-Login User Loader ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/')
def index():
    # MODIFIED: Redirect authenticated clients without subscription to pricing
    if current_user.is_authenticated:
        if current_user.role == 'client':
            if not has_active_subscription(current_user):
                flash("Please subscribe to a plan to access your dashboard.", "warning")
                return redirect(url_for('pricing'))
            return redirect(url_for('client_dashboard'))
        elif current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'therapist':
            return redirect(url_for('therapist_dashboard'))
        elif current_user.role == 'caregiver':
            return redirect(url_for('caregiver_dashboard'))
    # If not authenticated, or if it's a new client who just registered, show landing page
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            user.is_online = True
            user.last_online = datetime.utcnow()
            db.session.commit()
            socketio.emit('user_status_change', {'user_id': user.id, 'is_online': True, 'username': user.username}, room='admin_therapist_room')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')

@app.route("/register", methods=["GET", "POST"])
def register():
    # If user is already authenticated, redirect them to the login page (or their dashboard)
    if current_user.is_authenticated:
        return redirect(url_for('login'))

    if request.method == "POST":
        # Get form data
        username = request.form.get("username")
        role = request.form.get("role")
        email = request.form.get("email")
        name = request.form.get("name")

        # Basic validation
        if not username or not role or not email or not name:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Please choose a different one.", "danger")
            return redirect(url_for("register"))

        # Check if email already registered
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please use a different email.", "danger")
            return redirect(url_for("register"))

        # Generate one-time password
        password = secrets.token_hex(4)

        # Create new user instance
        new_user = User(username=username, email=email, name=name, role=role, is_online=False)
        new_user.set_password(password)

        # Attempt to add user to database
        try:
            db.session.add(new_user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration. Please try again.", "danger")
            print(f"Error committing new user to DB: {e}")
            return redirect(url_for("register"))

        # Email the one-time password - Direct msg.body version
        try:
            msg = Message("Your One-Time Login Password for GerioCare",
                            sender=app.config["MAIL_USERNAME"],
                            recipients=[email])
            msg.body = (
                f"Hello {new_user.name},\n\n"
                f"Your GerioCare account has been successfully created.\n"
                f"Your one-time password is:\n\n"
                f"{password}\n\n"
                f"Please log in using this password. We recommend changing your password after your first login for security.\n\n"
                f"You can log in here: {url_for('login', _external=True)}\n\n"
                f"If you have any questions or did not expect this email, please contact our support team.\n\n"
                f"Best regards,\n"
                f"The GerioCare IT Team\n\n"
                f"© {datetime.utcnow().year} GerioCare. All rights reserved.\n"
                f"Privacy Policy | Terms of Service"
            )
            mail.send(msg)
            flash("Registration successful. Check your email for your one-time password.", "success")
            print("✅ One-time password email sent successfully.")

        except socket.gaierror:
            flash("Registration successful, but could not send your password email due to a network issue. Please contact support to get your password.", "warning")
            print("⚠️ Network error: Could not send one-time password email.")
        except Exception as e:
            flash("Registration successful, but an error occurred while sending your password email. Please contact support to get your password.", "warning")
            print(f"❌ Error sending one-time password email: {e}")

        return redirect(url_for("login"))

    # For GET request, render the registration form
    return render_template("auth/register.html")

@app.route('/logout')
@login_required
def logout():
    current_user.is_online = False
    current_user.last_online = datetime.utcnow()
    db.session.commit()
    socketio.emit('user_status_change', {'user_id': current_user.id, 'is_online': False, 'username': current_user.username}, room='admin_therapist_room')

    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- Dashboard Routes ---

@app.route('/admin_dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    total_users = User.query.count()
    total_clients = User.query.filter_by(role='client').count()
    total_therapists = User.query.filter_by(role='therapist').count()
    total_admins = User.query.filter_by(role='admin').count()
    total_caregivers = User.query.filter_by(role='caregiver').count() # ADDED

    recent_users = User.query.order_by(User.id.desc()).limit(5).all()
    
    now_utc = datetime.utcnow()
    upcoming_appointments = Appointment.query.filter(
        Appointment.start_time >= now_utc,
        Appointment.start_time <= now_utc + timedelta(days=7)
    ).order_by(Appointment.start_time.asc()).limit(5).all()

    recent_assessments = PatientAssessment.query.order_by(PatientAssessment.submitted_at.desc()).limit(5).all()

    return render_template('dashboards/admin_dashboard.html',
                            total_users=total_users,
                            total_clients=total_clients,
                            total_therapists=total_therapists,
                            total_admins=total_admins,
                            total_caregivers=total_caregivers, # ADDED
                            recent_users=recent_users,
                            upcoming_appointments=upcoming_appointments,
                            recent_assessments=recent_assessments)


@app.route('/therapist_dashboard')
@login_required
@role_required('therapist', 'admin')
def therapist_dashboard():
    my_clients = User.query.filter_by(role='client').all() 

    # ADDED: Get caregivers for these clients, to allow messaging them
    clients_with_caregivers = []
    for client in my_clients:
        caregivers = client.caregivers_of_client.all() # Fetch linked caregivers for each client
        clients_with_caregivers.append({'client': client, 'caregivers': caregivers})


    now_utc = datetime.utcnow()
    upcoming_appointments = Appointment.query.filter(
        Appointment.therapist_id == current_user.id,
        Appointment.start_time >= now_utc
    ).order_by(Appointment.start_time.asc()).limit(5).all()

    recent_assigned_tasks = Task.query.filter(
        Task.therapist_id == current_user.id
    ).order_by(Task.created_at.desc()).limit(5).all()

    recent_assessments_submitted = PatientAssessment.query.filter(
        PatientAssessment.therapist_id == current_user.id
    ).order_by(PatientAssessment.submitted_at.desc()).limit(5).all()

    return render_template('dashboards/therapist_dashboard.html',
                            my_clients=my_clients, # Keep for general list
                            clients_with_caregivers=clients_with_caregivers, # ADDED: For messaging caregivers
                            upcoming_appointments=upcoming_appointments,
                            recent_assigned_tasks=recent_assigned_tasks,
                            recent_assessments_submitted=recent_assessments_submitted)


@app.route('/client_dashboard')
@login_required
@role_required('client', 'admin')
@subscription_required
def client_dashboard():
    now_utc = datetime.utcnow()
    upcoming_appointments = Appointment.query.filter(
        Appointment.client_id == current_user.id,
        Appointment.start_time >= now_utc
    ).order_by(Appointment.start_time.asc()).limit(5).all()

    assigned_tasks = Task.query.filter(
        Task.client_id == current_user.id,
        Task.status == 'pending'
    ).order_by(Task.due_date.asc()).limit(5).all()

    recent_assessments_for_client = PatientAssessment.query.filter(
        PatientAssessment.client_id == current_user.id
    ).order_by(PatientAssessment.submitted_at.desc()).limit(5).all()

    # MODIFIED: Fetch actual linked caregivers
    linked_caregivers = current_user.caregivers_of_client.all()
    
    # MODIFIED: Fetch actual linked therapists (if a client has a primary therapist or multiple)
    # For now, let's find therapists who have scheduled appointments for this client
    linked_therapists = User.query.join(Appointment, User.id == Appointment.therapist_id).filter(
        Appointment.client_id == current_user.id
    ).distinct().all()

    return render_template('dashboards/client_dashboard.html',
                            upcoming_appointments=upcoming_appointments,
                            assigned_tasks=assigned_tasks,
                            recent_assessments_for_client=recent_assessments_for_client,
                            linked_caregivers=linked_caregivers, # MODIFIED
                            linked_therapists=linked_therapists) # MODIFIED


@app.route('/caregiver_dashboard') # ADDED: New Caregiver Dashboard Route
@login_required
@role_required('caregiver', 'admin')
def caregiver_dashboard():
    managed_clients = current_user.clients_managed.all()

    # Fetch upcoming appointments for managed clients
    upcoming_appointments = []
    for client in managed_clients:
        client_appts = Appointment.query.filter(
            Appointment.client_id == client.id,
            Appointment.start_time >= datetime.utcnow()
        ).order_by(Appointment.start_time.asc()).all()
        upcoming_appointments.extend(client_appts)
    # Sort all collected appointments by time
    upcoming_appointments.sort(key=lambda x: x.start_time)
    # Limit to top 5 for dashboard overview
    upcoming_appointments = upcoming_appointments[:5]

    # Fetch pending tasks for managed clients
    pending_tasks = []
    for client in managed_clients:
        client_tasks = Task.query.filter(
            Task.client_id == client.id,
            Task.status == 'pending'
        ).order_by(Task.due_date.asc()).all()
        pending_tasks.extend(client_tasks)
    # Sort all collected tasks by due date
    pending_tasks.sort(key=lambda x: x.due_date if x.due_date else datetime.max)
    # Limit to top 5 for dashboard overview
    pending_tasks = pending_tasks[:5]

    # Fetch recent assessments for managed clients
    recent_assessments = []
    for client in managed_clients:
        client_assessments = PatientAssessment.query.filter(
            PatientAssessment.client_id == client.id
        ).order_by(PatientAssessment.submitted_at.desc()).all()
        recent_assessments.extend(client_assessments)
    recent_assessments.sort(key=lambda x: x.submitted_at, reverse=True)
    recent_assessments = recent_assessments[:5]


    return render_template('dashboards/caregiver_dashboard.html',
                            managed_clients=managed_clients,
                            upcoming_appointments=upcoming_appointments,
                            pending_tasks=pending_tasks,
                            recent_assessments=recent_assessments)


# --- Appointment Routes ---
@app.route('/appointments', methods=['GET', 'POST'])
@login_required
@subscription_required
def appointments():
    if request.method == 'POST':
        if current_user.role == 'therapist':
            client_id = request.form.get('client_id')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            notes = request.form.get('notes')

            try:
                start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
                end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
                if end_time <= start_time:
                    flash('End time must be after start time.', 'danger')
                    return redirect(url_for('appointments'))

                new_appointment = Appointment(
                    client_id=client_id,
                    therapist_id=current_user.id,
                    start_time=start_time,
                    end_time=end_time,
                    notes=notes
                )
                db.session.add(new_appointment)
                db.session.commit()
                flash('Appointment scheduled successfully!', 'success')

                client = User.query.get(client_id)
                if client:
                    alert_message = f"New appointment scheduled with {current_user.name} on {start_time.strftime('%Y-%m-%d at %H:%M')}"
                    new_alert = Alert(user_id=client.id, type='appointment_scheduled', message=alert_message)
                    db.session.add(new_alert)
                    db.session.commit()
                    socketio.emit('new_alert', {'message': alert_message}, room=f'user_{client.id}')

            except ValueError:
                flash('Invalid date/time format.', 'danger')
            except Exception as e:
                db.session.rollback()
                flash(f'Error scheduling appointment: {e}', 'danger')
                print(f"Appointment scheduling error: {e}")
        else:
            flash('Only therapists can schedule appointments.', 'danger')
        return redirect(url_for('appointments'))

    if current_user.role == 'therapist':
        all_appointments = Appointment.query.filter_by(therapist_id=current_user.id).order_by(Appointment.start_time.asc()).all()
        clients = User.query.filter_by(role='client').all()
        return render_template('appointments/appointments.html', appointments=all_appointments, clients=clients)
    elif current_user.role == 'caregiver': # ADDED: Caregiver view appointments
        managed_clients = current_user.clients_managed.all()
        client_ids = [client.id for client in managed_clients]
        all_appointments = Appointment.query.filter(Appointment.client_id.in_(client_ids)).order_by(Appointment.start_time.asc()).all()
        return render_template('appointments/appointments.html', appointments=all_appointments, clients=managed_clients) # Pass managed clients for context
    else: # Client view
        my_appointments = Appointment.query.filter_by(client_id=current_user.id).order_by(Appointment.start_time.asc()).all()
        return render_template('appointments/appointments.html', appointments=my_appointments)

# --- Messaging Routes ---
@app.route('/messages', methods=['GET', 'POST'])
@login_required
@subscription_required
def messages():
    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id')
        content = request.form.get('content')

        if not receiver_id or not content:
            flash('Recipient and message content are required.', 'danger')
            return redirect(url_for('messages'))

        receiver = User.query.get(receiver_id)
        if not receiver:
            flash('Recipient not found.', 'danger')
            return redirect(url_for('messages'))

        new_message = UserMessage(sender_id=current_user.id, receiver_id=receiver_id, content=content)
        db.session.add(new_message)
        db.session.commit()
        flash('Message sent!', 'success')

        socketio.emit('new_message', {
            'sender_id': current_user.id,
            'sender_name': current_user.name,
            'content': content,
            'timestamp': new_message.timestamp.strftime('%Y-%m-%d %H:%M')
        }, room=f'user_{receiver_id}')

        return redirect(url_for('messages'))

    # GET request logic
    users_to_message = []
    if current_user.role == 'therapist':
        clients = User.query.filter_by(role='client').all()
        caregivers = User.query.filter_by(role='caregiver').all()
        users_to_message.extend(clients)
        users_to_message.extend(caregivers)
    elif current_user.role == 'client':
        therapists = User.query.filter_by(role='therapist').all()
        caregivers = current_user.caregivers_of_client.all()
        users_to_message.extend(therapists)
        users_to_message.extend(caregivers)
    elif current_user.role == 'caregiver':
        managed_clients = current_user.clients_managed.all()
        therapists = User.query.filter_by(role='therapist').all()
        users_to_message.extend(managed_clients)
        users_to_message.extend(therapists)
    else: # Admin can message anyone
        users_to_message = User.query.filter(User.id != current_user.id).all()

    # Ensure partner objects are fully loaded or converted for JSON serialization
    cleaned_users_to_message = []
    for u in users_to_message:
        cleaned_users_to_message.append({
            'id': u.id,
            'name': u.name,
            'username': u.username,
            'role': u.role,
            'is_online': u.is_online
        })
    users_to_message = sorted(list({u['id']: u for u in cleaned_users_to_message}.values()), key=lambda u: u['name'])


    all_messages = UserMessage.query.filter(
        (UserMessage.sender_id == current_user.id) | (UserMessage.receiver_id == current_user.id)
    ).order_by(UserMessage.timestamp.asc()).all()

    conversations = {}
    # First, populate conversations with all potential partners, even if no messages yet
    for user_data in users_to_message:
        conversations[user_data['id']] = {
            'partner': user_data,
            'messages': [],
            'unread_count': 0
        }

    # Then, add actual messages to their respective conversations
    for msg in all_messages:
        partner_id = msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        
        # Ensure the partner exists in the conversations dict, if not, create a minimal entry
        if partner_id not in conversations:
            partner_user = User.query.get(partner_id)
            if partner_user:
                conversations[partner_id] = {
                    'partner': {
                        'id': partner_user.id,
                        'name': partner_user.name,
                        'username': partner_user.username,
                        'role': partner_user.role,
                        'is_online': partner_user.is_online
                    },
                    'messages': [],
                    'unread_count': 0
                }
            else:
                # Fallback for truly unknown users (should be rare with FKs)
                conversations[partner_id] = {
                    'partner': {'id': partner_id, 'name': 'Unknown User', 'username': 'unknown', 'role': 'unknown', 'is_online': False},
                    'messages': [],
                    'unread_count': 0
                }

        if msg.receiver_id == current_user.id and not msg.is_read:
            msg.is_read = True
            db.session.add(msg)
            conversations[partner_id]['unread_count'] += 1

        conversations[partner_id]['messages'].append({
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M'),
            'is_read': msg.is_read
        })
    db.session.commit()

    print("Conversations data being passed to template:")
    for p_id, conv_data in conversations.items():
        print(f"  Partner ID: {p_id}, Partner Name: {conv_data['partner']['name']}, Messages Count: {len(conv_data['messages'])}")
        if len(conv_data['messages']) > 0:
            print(f"    First message content: {conv_data['messages'][0]['content']}")


    return render_template('messages/messages.html', users_to_message=users_to_message, conversations=conversations)


# --- Forms Routes ---
@app.route('/forms')
@login_required
@subscription_required
def forms_selection():
    # MODIFIED: Caregivers can also access forms (e.g., to view filled forms)
    # if current_user.role not in ['therapist', 'admin', 'caregiver']:
    #     flash('Access denied.', 'danger')
    #     return redirect(url_for('index'))
    return render_template('forms/form_selection.html')

@app.route('/forms/outpatient', methods=['GET', 'POST'])
@login_required
@role_required('therapist', 'admin')
@subscription_required
def outpatient_form():
    # MODIFIED: Only therapists can fill forms
    # if current_user.role != 'therapist':
    #     flash('Access denied. Only therapists can fill this form.', 'danger')
    #     return redirect(url_for('forms_selection'))

    clients = User.query.filter_by(role='client').all()

    if request.method == 'POST':
        client_id = request.form.get('client_id')
        if not client_id:
            flash('Please select a client.', 'danger')
            return render_template('forms/outpatient_form.html', clients=clients)

        form_data = {key: request.form.get(key) for key in request.form if key != 'client_id'}
        checkbox_fields = [
            'adls', 'iadls', 'rest_and_sleep', 'education', 'work', 'play', 'leisure', 'social_participation',
            'motor_skills', 'process_skills', 'social_interaction_skills',
            'habits', 'routines', 'roles', 'rituals',
            'environmental', 'personal', 'cultural', 'temporal', 'virtual',
            'body_functions', 'body_structures', 'values', 'beliefs', 'spirituality',
            'create_promote', 'establish_restore', 'maintain', 'modify', 'prevent',
            'copm', 'gas', 'fim', 'observation', 'other_outcome_tool'
        ]
        for field in checkbox_fields:
            form_data[field] = 'on' if request.form.get(field) else 'off'

        new_assessment = PatientAssessment(
            therapist_id=current_user.id,
            client_id=client_id,
            form_type='outpatient',
            form_data_json=json.dumps(form_data)
        )
        db.session.add(new_assessment)
        db.session.commit()
        flash('Outpatient assessment submitted successfully!', 'success')
        return redirect(url_for('therapist_dashboard'))

    return render_template('forms/outpatient_form.html', clients=clients)

@app.route('/forms/home_health', methods=['GET', 'POST'])
@login_required
@role_required('therapist', 'admin')
@subscription_required
def home_health_form():
    # MODIFIED: Only therapists can fill forms
    # if current_user.role != 'therapist':
    #     flash('Access denied. Only therapists can fill this form.', 'danger')
    #     return redirect(url_for('forms_selection'))

    clients = User.query.filter_by(role='client').all()

    if request.method == 'POST':
        client_id = request.form.get('client_id')
        if not client_id:
            flash('Please select a client.', 'danger')
            return render_template('forms/home_health_form.html', clients=clients)

        form_data = {key: request.form.get(key) for key in request.form if key != 'client_id'}
        checkbox_fields = [
            'lives_alone', 'with_spouse_partner', 'with_family', 'assisted_living', 'other_living',
            'bathing', 'dressing', 'toileting', 'eating', 'grooming', 'other_self_care',
            'stairs', 'grab_bars', 'ramp', 'none_safety', 'other_safety',
            'walker', 'wheelchair', 'cane', 'hearing_aid', 'glasses'
        ]
        for field in checkbox_fields:
            if field in request.form:
                form_data[field] = 'on'
            else:
                form_data[field] = 'off'

        radio_fields = ['level_of_assistance', 'difficulties_with_iadls']
        for field in radio_fields:
            if request.form.get(field):
                form_data[field] = request.form.get(field)
            else:
                form_data[field] = None

        new_assessment = PatientAssessment(
            therapist_id=current_user.id,
            client_id=client_id,
            form_type='home_health',
            form_data_json=json.dumps(form_data)
        )
        db.session.add(new_assessment)
        db.session.commit()
        flash('Home Health assessment submitted successfully!', 'success')
        return redirect(url_for('therapist_dashboard'))

    return render_template('forms/home_health_form.html', clients=clients)


# --- Profile Management Routes ---
@app.route('/profile', methods=['GET', 'POST'])
@login_required
@subscription_required
def profile_edit():
    user = current_user
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_email = request.form.get('email')
        new_username = request.form.get('username')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_name and new_name != user.name:
            user.name = new_name
            flash('Name updated successfully!', 'success')
        
        if new_email and new_email != user.email:
            if User.query.filter_by(email=new_email).first() and User.query.filter_by(email=new_email).first().id != user.id:
                flash('Email already taken.', 'danger')
            else:
                user.email = new_email
                flash('Email updated successfully!', 'success')

        if new_username and new_username != user.username:
            if User.query.filter_by(username=new_username).first() and User.query.filter_by(username=new_username).first().id != user.id:
                flash('Username already taken.', 'danger')
            else:
                user.username = new_username
                flash('Username updated successfully!', 'success')

        if new_password:
            if not current_password or not user.check_password(current_password):
                flash('Incorrect current password.', 'danger')
            elif new_password != confirm_password:
                flash('New password and confirm password do not match.', 'danger')
            else:
                user.set_password(new_password)
                flash('Password updated successfully!', 'success')
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating profile: {e}', 'danger')
            print(f"Profile update error: {e}")

        return redirect(url_for('profile_edit'))

    return render_template('profile/profile_edit.html', user=user)


# --- Task Management Routes ---
@app.route('/tasks', methods=['GET'])
@login_required
@subscription_required
def tasks():
    if current_user.role == 'therapist':
        assigned_tasks = Task.query.filter_by(therapist_id=current_user.id).order_by(Task.due_date.asc()).all()
        clients = User.query.filter_by(role='client').all()

        return render_template('tasks/therapist_tasks.html', 
                                assigned_tasks=assigned_tasks, 
                                clients=clients)
    elif current_user.role == 'client':
        my_tasks = Task.query.filter_by(client_id=current_user.id).order_by(Task.due_date.asc()).all()
        return render_template('tasks/client_tasks.html', my_tasks=my_tasks)
    elif current_user.role == 'caregiver': # ADDED: Caregiver can view tasks for their managed clients
        managed_clients = current_user.clients_managed.all()
        client_ids = [client.id for client in managed_clients]
        tasks_for_managed_clients = Task.query.filter(Task.client_id.in_(client_ids)).order_by(Task.due_date.asc()).all()
        return render_template('tasks/caregiver_tasks.html', tasks_for_managed_clients=tasks_for_managed_clients) # ADDED: New template for caregiver tasks
    else:
        flash('Access denied to tasks.', 'danger')
        return redirect(url_for('index'))

@app.route('/tasks/assign', methods=['POST'])
@login_required
@role_required('therapist', 'admin')
@subscription_required
def assign_task():
    # if current_user.role != 'therapist':
    #     flash('Access denied. Only therapists can assign tasks.', 'danger')
    #     return redirect(url_for('tasks'))

    client_id = request.form.get('client_id')
    title = request.form.get('title')
    description = request.form.get('description')
    due_date_str = request.form.get('due_date')
    image_url = request.form.get('uploaded_image_url')
    video_url = request.form.get('uploaded_video_url')

    if not client_id or not title:
        flash('Client and task title are required.', 'danger')
        return redirect(url_for('tasks'))

    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M') if due_date_str else None
        
        new_task = Task(
            client_id=client_id,
            therapist_id=current_user.id,
            title=title,
            description=description,
            due_date=due_date,
            status='pending',
            image_url=image_url if image_url else None, # ADDED
            video_url=video_url if video_url else None # ADDED
        )
        db.session.add(new_task)
        db.session.commit()
        flash('Task assigned successfully!', 'success')

        client = User.query.get(client_id)
        if client:
            alert_message = f"You have a new task: '{title}' assigned by {current_user.name}."
            new_alert = Alert(user_id=client.id, type='new_task', message=alert_message)
            db.session.add(new_alert)
            db.session.commit()
            socketio.emit('new_alert', {'message': alert_message}, room=f'user_{client.id}')

    except ValueError:
        flash('Invalid due date format.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error assigning task: {e}', 'danger')
        print(f"Task assignment error: {e}")

    return redirect(url_for('tasks'))

@app.route('/tasks/complete/<int:task_id>', methods=['POST'])
@login_required
@subscription_required
def mark_task_complete(task_id):
    task = Task.query.get_or_404(task_id)
    # MODIFIED: Allow caregiver to mark tasks complete for their managed clients
    if task.client_id != current_user.id and \
        (current_user.role == 'caregiver' and task.client_id not in [c.id for c in current_user.clients_managed.all()]) and \
        task.therapist_id != current_user.id:
        flash('You are not authorized to mark this task complete.', 'danger')
        return redirect(url_for('tasks'))

    if task.status == 'completed':
        flash('Task is already marked as completed.', 'info')
        return redirect(url_for('tasks'))

    task.status = 'completed'
    task.completed_at = datetime.utcnow()
    try:
        db.session.commit()
        flash('Task marked as completed!', 'success')

        if current_user.role == 'client':
            therapist = User.query.get(task.therapist_id)
            if therapist:
                alert_message = f"Client {current_user.name} has completed task: '{task.title}'."
                new_alert = Alert(user_id=therapist.id, type='task_completed', message=alert_message)
                db.session.add(new_alert)
                db.session.commit()
                socketio.emit('new_alert', {'message': alert_message}, room=f'user_{therapist.id}')
        elif current_user.role == 'caregiver': # ADDED: Notify therapist if caregiver marks task complete
            therapist = User.query.get(task.therapist_id)
            if therapist:
                alert_message = f"Caregiver {current_user.name} marked task '{task.title}' for client {task.client_user.name} as complete."
                new_alert = Alert(user_id=therapist.id, type='task_completed', message=alert_message)
                db.session.add(new_alert)
                db.session.commit()
                socketio.emit('new_alert', {'message': alert_message}, room=f'user_{therapist.id}')


    except Exception as e:
        db.session.rollback()
        flash(f'Error marking task complete: {e}', 'danger')
        print(f"Mark task complete error: {e}")

    return redirect(url_for('tasks'))

@app.route('/upload_media', methods=['POST'])
@login_required
@role_required('therapist', 'admin')
@subscription_required
def upload_media():
    # if current_user.role != 'therapist':
    #     return jsonify({'error': 'Access denied. Only therapists can upload media.'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    file_extension = file.filename.rsplit('.', 1)[1].lower()
    
    if allowed_file(file.filename, app.config['ALLOWED_IMAGE_EXTENSIONS']):
        file_type = 'image'
        if not allowed_file(file.filename, app.config['ALLOWED_IMAGE_EXTENSIONS']):
            return jsonify({'error': 'Invalid image file type'}), 400
    elif allowed_file(file.filename, app.config['ALLOWED_VIDEO_EXTENSIONS']):
        file_type = 'video'
        if not allowed_file(file.filename, app.config['ALLOWED_VIDEO_EXTENSIONS']):
            return jsonify({'error': 'Invalid video file type'}), 400
    else:
        return jsonify({'error': 'Unsupported file type'}), 400

    try:
        # Generate a unique filename
        unique_filename = str(uuid.uuid4()) + '.' + file_extension
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(unique_filename))
        file.save(filepath)

        thumbnail_url = None
        if file_type == 'image':
            thumbnail_filename = f"thumb_{unique_filename}"
            thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], secure_filename(thumbnail_filename))
            if generate_image_thumbnail(filepath, thumbnail_path):
                thumbnail_url = url_for('static', filename=f'uploads/tasks/thumbnails/{secure_filename(thumbnail_filename)}')
            else:
                # If thumbnail generation fails, use the original image as thumbnail
                thumbnail_url = url_for('static', filename=f'uploads/tasks/{secure_filename(unique_filename)}')
        elif file_type == 'video':
            thumbnail_filename = f"thumb_{os.path.splitext(unique_filename)[0]}.jpg" # Video thumbnails are usually JPG
            thumbnail_path = os.path.join(app.config['THUMBNAIL_FOLDER'], secure_filename(thumbnail_filename))
            if generate_video_thumbnail(filepath, thumbnail_path):
                thumbnail_url = url_for('static', filename=f'uploads/tasks/thumbnails/{secure_filename(thumbnail_filename)}')
            # If video thumbnail generation fails, provide a generic video icon/placeholder
            else:
                thumbnail_url = url_for('static', filename='images/video_placeholder.png') # You might need to create this image

        # Construct URL relative to static folder
        media_url = url_for('static', filename=f'uploads/tasks/{secure_filename(unique_filename)}')

        return jsonify({'success': True, 'file_type': file_type, 'url': media_url, 'thumbnail_url': thumbnail_url}), 200

    except Exception as e:
        print(f"Error during file upload: {e}")
        return jsonify({'error': f'Failed to upload file: {e}'}), 500

# --- NEW ROUTES FOR LISTING PAGES ---
@app.route('/users_list')
@login_required
@role_required('admin')
def users_list():
    # if current_user.role != 'admin':
    #     flash('Access denied. Only administrators can view all users.', 'danger')
    #     return redirect(url_for('index'))
    
    all_users = User.query.order_by(User.name.asc()).all()
    return render_template('users/users_list.html', users=all_users)

@app.route('/assessments_list')
@login_required
@subscription_required
def assessments_list():
    # if current_user.role not in ['admin', 'therapist', 'caregiver']: # MODIFIED: Caregivers can view assessments
    #     flash('Access denied. Only administrators, therapists, and caregivers can view assessments.', 'danger')
    #     return redirect(url_for('index'))
    
    if current_user.role == 'therapist':
        all_assessments = PatientAssessment.query.filter(
            PatientAssessment.therapist_id == current_user.id
        ).order_by(PatientAssessment.submitted_at.desc()).all()
    elif current_user.role == 'caregiver': # ADDED: Caregiver view assessments for managed clients
        managed_clients = current_user.clients_managed.all()
        client_ids = [client.id for client in managed_clients]
        all_assessments = PatientAssessment.query.filter(
            PatientAssessment.client_id.in_(client_ids)
        ).order_by(PatientAssessment.submitted_at.desc()).all()
    else: # Admin
        all_assessments = PatientAssessment.query.order_by(PatientAssessment.submitted_at.desc()).all()
    
    return render_template('assessments/assessments_list.html', assessments=all_assessments)

@app.route('/alerts')
@login_required
@subscription_required
def alerts():
    user_alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.timestamp.desc()).all()
    
    for alert in user_alerts:
        if not alert.is_read:
            alert.is_read = True
            db.session.add(alert)
    db.session.commit()

    return render_template('alerts/alerts_list.html', alerts=user_alerts)

@app.route('/mark_alert_read/<int:alert_id>', methods=['POST'])
@login_required
@subscription_required
def mark_alert_read(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    if alert.user_id != current_user.id:
        flash('You are not authorized to mark this alert.', 'danger')
        return redirect(url_for('alerts'))
    
    alert.is_read = True
    try:
        db.session.commit()
        flash('Alert marked as read.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error marking alert as read: {e}', 'danger')
        print(f"Mark alert read error: {e}")
    
    return redirect(url_for('alerts'))

# ADDED: Route to link a caregiver to a client (Admin/Therapist functionality)
@app.route('/link_caregiver', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'therapist')
def link_caregiver():
    # if current_user.role not in ['admin', 'therapist']:
    #     flash('Access denied. Only administrators and therapists can link caregivers.', 'danger')
    #     return redirect(url_for('index'))

    clients = User.query.filter_by(role='client').order_by(User.name.asc()).all()
    caregivers = User.query.filter_by(role='caregiver').order_by(User.name.asc()).all()

    if request.method == 'POST':
        client_id = request.form.get('client_id')
        caregiver_id = request.form.get('caregiver_id')

        client = User.query.get(client_id)
        caregiver = User.query.get(caregiver_id)

        if not client or client.role != 'client':
            flash('Invalid client selected.', 'danger')
            return redirect(url_for('link_caregiver'))
        if not caregiver or caregiver.role != 'caregiver':
            flash('Invalid caregiver selected.', 'danger')
            return redirect(url_for('link_caregiver'))

        # Check if already linked
        if caregiver in client.caregivers_of_client:
            flash(f'{caregiver.name} is already linked to {client.name}.', 'info')
        else:
            try:
                client.caregivers_of_client.append(caregiver)
                db.session.commit()
                flash(f'{caregiver.name} successfully linked to {client.name}.', 'success')
                # Send alert to caregiver
                alert_message = f"You have been linked as a caregiver to client: {client.name}."
                new_alert = Alert(user_id=caregiver.id, type='caregiver_link', message=alert_message)
                db.session.add(new_alert)
                db.session.commit()
                socketio.emit('new_alert', {'message': alert_message}, room=f'user_{caregiver.id}')

            except Exception as e:
                db.session.rollback()
                flash(f'Error linking caregiver: {e}', 'danger')
                print(f"Error linking caregiver: {e}")
        
        return redirect(url_for('link_caregiver'))

    return render_template('users/link_caregiver.html', clients=clients, caregivers=caregivers)


# NEW: Paystack Subscription Routes
@app.route("/pricing")
def pricing():
    plans = Plan.query.filter_by(is_active=True).all()
    # current_utc_year = datetime.now(timezone.utc).year # 'now' is already in context processor
    return render_template("pricing.html",
                           plans=plans,
                           pub_key=app.config["PAYSTACK_PUBLIC_KEY"]) # Pass public key to frontend
    
@app.post("/ps_webhook")
def paystack_webhook():
    """
    Handles Paystack webhook notifications for successful charges.
    """
    raw = request.get_data()
    sign = request.headers.get("x-paystack-signature", "")
    secret = app.config["PAYSTACK_WEBHOOK_SECRET"].encode()

    # Verify webhook signature
    if hmac.new(secret, raw, hashlib.sha512).hexdigest() != sign:
        print("⚠️ Paystack Webhook: Invalid signature.")
        abort(400) # Bad request if signature doesn't match

    event = json.loads(raw)
    print(f"✅ Paystack Webhook received event: {event.get('event')}")

    if event["event"] == "charge.success":
        ref = event["data"]["reference"]
        _handle_charge_success(ref)
    
    return {"status": "ok"}, 200 # Always return 200 OK to Paystack

def _handle_charge_success(ref):
    """
    Handles successful charge event from Paystack webhook.
    Updates subscription status.
    """
    # 1. Get the subscription by reference
    # Note: 'ref' is unique in Subscription model
    sub = Subscription.query.filter_by(ref=ref).first()
    if not sub:
        print(f"⚠️ Paystack Webhook: No subscription found for reference {ref}. This might be an issue if verification happened out of order or reference is wrong.")
        return

    # 2. Update the subscription status and expiry
    # The webhook confirms the payment, so we can activate it here
    sub.status = "active"
    # Ensure expires_at is correctly set based on the plan's interval
    if sub.plan:
        sub.expires_at = datetime.utcnow() + timedelta(days=sub.plan.interval_days)
    else:
        # Fallback if plan somehow not found (shouldn't happen if plan_id is FK)
        sub.expires_at = datetime.utcnow() + timedelta(days=30) # Default to 30 days if plan missing
        print(f"⚠️ Paystack Webhook: Plan not found for subscription {sub.id}. Defaulting expiry to 30 days.")

    db.session.commit()
    print(f"✅ Paystack Webhook: Subscription {sub.id} activated for user {sub.user.username} with reference {ref}.")

    # Optional: Notify user or admin
    # send_app_alert(sub.user_id, 'subscription_active', f"Your subscription to {sub.plan.name} is now active!")


@app.route("/paystack/verify", methods=["POST"])
@login_required
@role_required('client') # Only clients can verify payments for their subscriptions
def verify_payment():
    """
    Endpoint for frontend to verify a Paystack transaction after user completes payment.
    """
    data = request.get_json()
    ref = data.get("ref")
    plan_id = data.get("plan_id")

    if not ref or not plan_id:
        return jsonify({"error": "Missing transaction reference or plan ID."}), 400

    plan = Plan.query.get(plan_id)
    if not plan:
        return jsonify({"error": "Invalid plan selected."}), 400

    # Verify with Paystack API
    url = f"https://api.paystack.co/transaction/verify/{ref}"
    
    try:
        res = requests.get(url, headers=PAYSTACK_HEADERS, timeout=10)
        res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        response = res.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Paystack API request failed: {e}")
        return jsonify({"error": "Failed to connect to payment gateway. Please try again."}), 500
    except json.JSONDecodeError as e:
        print(f"ERROR: Paystack API response not valid JSON: {res.text} - {e}")
        return jsonify({"error": "Invalid response from payment gateway."}), 500

    if response.get("status") and response["data"]["status"] == "success":
        # Check if the amount paid matches the plan amount
        amount_paid = response["data"]["amount"] # in kobo/pesewas
        if amount_paid < plan.amount_pesewas:
            print(f"WARNING: Amount mismatch for ref {ref}. Expected {plan.amount_pesewas}, got {amount_paid}.")
            # You might want to handle this as a partial payment or failure
            return jsonify({"error": "Payment amount mismatch. Please contact support."}), 400

        # Store or update subscription
        # Check if a subscription with this ref already exists (e.g., from webhook)
        sub = Subscription.query.filter_by(ref=ref).first()
        if not sub:
            # Create new subscription if not already created by webhook
            sub = Subscription(
                user_id=current_user.id,
                plan_id=plan.id,
                ref=ref,
                timestamp=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=plan.interval_days),
                status='active' # Mark as active immediately after verification
            )
            db.session.add(sub)
            db.session.commit()
            print(f"✅ Subscription created and activated for user {current_user.username} with ref {ref} via API verification.")
        elif sub.status != 'active':
            # Update existing subscription if it was pending or something
            sub.status = 'active'
            sub.expires_at = datetime.utcnow() + timedelta(days=plan.interval_days) # Update expiry
            db.session.commit()
            print(f"✅ Existing subscription {sub.id} updated to active for user {current_user.username} with ref {ref}.")
        
        return jsonify({"success": True, "message": "Payment successful and subscription activated!"})

    # If Paystack verification status is not success
    error_message = response.get("message", "Payment verification failed. Please try again.")
    print(f"❌ Paystack Verification Failed for ref {ref}: {error_message}")
    return jsonify({"error": error_message}), 400


@app.route('/my_subscription')
@login_required # Only logged-in users can see their subscription details
@role_required('client', 'admin') # Only clients and admins can view this page
def my_subscription():
    # current_utc_year = datetime.now(timezone.utc).year # 'now' is already in context processor
    
    # If an admin is viewing, they might want to see a list of subscriptions or a specific one.
    # For simplicity, this route is client-focused. Admins can access it but it will show their (non-existent) subscription.
    # A more robust solution would have a separate admin view for subscriptions.
    
    if current_user.role == 'client':
        # Fetch the most recent subscription for the current client user
        latest_subscription = Subscription.query.filter_by(user_id=current_user.id)\
                                                .order_by(Subscription.timestamp.desc())\
                                                .first()
        return render_template('my_subscription.html',
                               subscription=latest_subscription,
                               datetime=datetime) # Pass datetime module for template comparisons
    else:
        # For therapist/caregiver, redirect them to their dashboard
        flash("You are not authorized to view this page.", 'danger')
        if current_user.role == 'therapist':
            return redirect(url_for('therapist_dashboard'))
        elif current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'caregiver':
            return redirect(url_for('caregiver_dashboard'))
        else:
            return redirect(url_for('index')) # Fallback for other roles


# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        current_user.is_online = True
        current_user.last_online = datetime.utcnow()
        db.session.commit()
        join_room(f'user_{current_user.id}')
        if current_user.role in ['admin', 'therapist']:
            join_room('admin_therapist_room')
            if current_user.role == 'client': # Only notify if a client comes online
                alert_message = f"Patient {current_user.name} is now online."
                new_alert = Alert(user_id=current_user.id, type='patient_online', message=alert_message)
                db.session.add(new_alert)
                db.session.commit()
                socketio.emit('patient_online_alert', {'user_id': current_user.id, 'username': current_user.username, 'message': alert_message}, room='admin_therapist_room')
        print(f'User {current_user.username} connected and is online.')
    else:
        print('Anonymous user connected.')

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        current_user.is_online = False
        current_user.last_online = datetime.utcnow()
        db.session.commit()
        leave_room(f'user_{current_user.id}')
        if current_user.role in ['admin', 'therapist']:
            leave_room('admin_therapist_room')
        print(f'User {current_user.username} disconnected and is offline.')
    else:
        print('Anonymous user disconnected.')

def send_app_alert(user_id, alert_type, message_content):
    new_alert = Alert(user_id=user_id, type=alert_type, message=message_content)
    db.session.add(new_alert)
    db.session.commit()
    socketio.emit('new_alert', {'message': message_content}, room=f'user_{user_id}')
    
    
# --- New Static Pages Routes ---
@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST']) # MODIFIED: Allow POST requests
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message_content = request.form.get('message')

        if not name or not email or not subject or not message_content:
            flash('All fields are required to send a message.', 'danger')
            return render_template('contact.html', name=name, email=email, subject=subject, message_content=message_content)

        try:
            msg = Message(subject=f"GerioCare Contact Form: {subject} from {name}",
                            sender=app.config["MAIL_USERNAME"], # This should be your configured sender email
                            recipients=[app.config["MAIL_USERNAME"]], # Send to your support email (same as sender for simplicity here)
                            body=f"Name: {name}\nEmail: {email}\n\nMessage:\n{message_content}")
            mail.send(msg)
            flash('Your message has been sent successfully! We will get back to you soon.', 'success')
            print(f"Contact form email sent from {email} with subject: {subject}")
            return redirect(url_for('contact')) # Redirect after successful submission to prevent resubmission
        except socket.gaierror:
            flash("Failed to send message due to a network issue. Please try again later.", "danger")
            print("⚠️ Network error: Could not send contact form email.")
        except Exception as e:
            flash("An error occurred while sending your message. Please try again.", "danger")
            print(f"❌ Error sending contact form email: {e}")

    return render_template('contact.html')


@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms_of_use')
def terms_of_use():
    return render_template('terms_of_use.html')

# --- Error Handlers (Optional, but good practice)
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


# --- Initial Database Setup and Run ---
if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(app.instance_path):
            os.makedirs(app.instance_path)

        db.create_all()
        
        # NEW: Add default plans if none exist
        if Plan.query.count() == 0:
            print("Adding default subscription plans...")
            monthly_plan = Plan(
                name="Monthly Plan",
                amount_pesewas=5000, # GHS 50.00
                interval_days=30,
                description="Access to core features for one month."
            )
            quarterly_plan = Plan(
                name="Quarterly Plan",
                amount_pesewas=12000, # GHS 120.00
                interval_days=90,
                description="Extended access and additional features for three months."
            )
            annual_plan = Plan(
                name="Annual Plan",
                amount_pesewas=40000, # GHS 400.00
                interval_days=365,
                description="Full access to all premium features for one year with a discount."
            )
            db.session.add_all([monthly_plan, quarterly_plan, annual_plan])
            db.session.commit()
            print("Default plans added: Monthly, Quarterly, Annual.")

        if User.query.count() == 0:
            admin_user = User(
                username='admin',
                email='admin@geriocare.com',
                name='Admin User',
                role='admin',
                is_online=False
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created: username='admin', password='admin123'")



    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)

