from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from sqlalchemy import Table, Column, Integer, ForeignKey
from sqlalchemy.orm import relationship


db = SQLAlchemy()

# Association table for many-to-many relationship between clients and caregivers
client_caregivers = db.Table('client_caregivers',
    db.Column('client_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('caregiver_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='client') # 'admin', 'therapist', 'client', 'caregiver'
    is_online = db.Column(db.Boolean, default=False)
    last_online = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    client_appointments = db.relationship('Appointment', foreign_keys='Appointment.client_id', backref='client', lazy=True)
    therapist_appointments = db.relationship('Appointment', foreign_keys='Appointment.therapist_id', backref='therapist', lazy=True)

    sent_messages = db.relationship('UserMessage', foreign_keys='UserMessage.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('UserMessage', foreign_keys='UserMessage.receiver_id', backref='receiver', lazy=True)

    alerts = db.relationship('Alert', backref='user', lazy=True)
    assigned_tasks = db.relationship('Task', foreign_keys='Task.client_id', backref='client_user', lazy=True)
    created_tasks = db.relationship('Task', foreign_keys='Task.therapist_id', backref='therapist_user', lazy=True)
    client_assessments = db.relationship('PatientAssessment', foreign_keys='PatientAssessment.client_id', backref='assessed_client', lazy=True)
    therapist_assessments = db.relationship('PatientAssessment', foreign_keys='PatientAssessment.therapist_id', backref='assessing_therapist', lazy=True)

    # Relationships for client-caregiver linking
    # For a client, list of caregivers associated with them
    caregivers_of_client = db.relationship(
        'User', secondary=client_caregivers,
        primaryjoin=(client_caregivers.c.client_id == id),
        secondaryjoin=(client_caregivers.c.caregiver_id == id),
        backref=db.backref('clients_managed', lazy='dynamic'),
        lazy='dynamic'
    )

    subscriptions = db.relationship('Subscription', backref='user', lazy=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='scheduled') # 'scheduled', 'completed', 'cancelled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Appointment {self.id} - Client: {self.client_id} - Therapist: {self.therapist_id}>'

class UserMessage(db.Model):
    __tablename__ = 'user_message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<UserMessage {self.id} - From: {self.sender_id} To: {self.receiver_id}>'

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False) # e.g., 'new_message', 'appointment_scheduled', 'patient_online'
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Alert {self.id} - User: {self.user_id} - Type: {self.type}>'

class PatientAssessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    form_type = db.Column(db.String(50), nullable=False) # 'outpatient', 'home_health'
    form_data_json = db.Column(db.Text, nullable=False) # Store form data as JSON string
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_form_data(self):
        return json.loads(self.form_data_json) if self.form_data_json else {}

    def __repr__(self):
        return f'<PatientAssessment {self.id} - Client: {self.client_id} - Type: {self.form_type}>'

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Who assigned the task
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending') # 'pending', 'completed', 'overdue'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    image_url = db.Column(db.String(500), nullable=True) # ADDED: For task illustration image
    video_url = db.Column(db.String(500), nullable=True) # ADDED: For task illustration video

    def __repr__(self):
        return f'<Task {self.id} - Client: {self.client_id} - Title: {self.title}>'

# NEW: Plan Model for Subscription Tiers
class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    amount_pesewas = db.Column(db.Integer, nullable=False) # Amount in smallest currency unit (e.g., pesewas for GHS)
    interval_days = db.Column(db.Integer, nullable=False) # e.g., 30 for monthly, 90 for quarterly, 365 for yearly
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True) # Can be deactivated by admin if no longer offered
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subscriptions = db.relationship('Subscription', backref='plan', lazy=True)

    def __repr__(self):
        return f"<Plan {self.name} - {self.amount_pesewas / 100} GHS>"

# NEW: Subscription Model for User Subscriptions
class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), nullable=False)
    ref = db.Column(db.String(255), unique=True, nullable=False) # Paystack transaction reference
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default='pending') # 'pending', 'active', 'expired', 'cancelled'

    def __repr__(self):
        return f"<Subscription {self.id} for User {self.user_id} (Plan: {self.plan_id}, Status: {self.status})>"









# from flask_sqlalchemy import SQLAlchemy
# from flask_login import UserMixin
# from werkzeug.security import generate_password_hash, check_password_hash
# from datetime import datetime
# import json

# db = SQLAlchemy()

# # ADDED: Association table for many-to-many relationship between clients and caregivers
# client_caregivers = db.Table('client_caregivers',
#     db.Column('client_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
#     db.Column('caregiver_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
# )

# class User(UserMixin, db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80), unique=True, nullable=False)
#     email = db.Column(db.String(120), unique=True, nullable=False)
#     name = db.Column(db.String(120), nullable=False)
#     password_hash = db.Column(db.String(128), nullable=False)
#     role = db.Column(db.String(20), nullable=False, default='client') # 'admin', 'therapist', 'client', 'caregiver'
#     is_online = db.Column(db.Boolean, default=False)
#     last_online = db.Column(db.DateTime, default=datetime.utcnow)

#     # Relationships
#     client_appointments = db.relationship('Appointment', foreign_keys='Appointment.client_id', backref='client', lazy=True)
#     therapist_appointments = db.relationship('Appointment', foreign_keys='Appointment.therapist_id', backref='therapist', lazy=True)

#     sent_messages = db.relationship('UserMessage', foreign_keys='UserMessage.sender_id', backref='sender', lazy=True)
#     received_messages = db.relationship('UserMessage', foreign_keys='UserMessage.receiver_id', backref='receiver', lazy=True)

#     alerts = db.relationship('Alert', backref='user', lazy=True)
#     assigned_tasks = db.relationship('Task', foreign_keys='Task.client_id', backref='client_user', lazy=True)
#     created_tasks = db.relationship('Task', foreign_keys='Task.therapist_id', backref='therapist_user', lazy=True)
#     client_assessments = db.relationship('PatientAssessment', foreign_keys='PatientAssessment.client_id', backref='assessed_client', lazy=True)
#     therapist_assessments = db.relationship('PatientAssessment', foreign_keys='PatientAssessment.therapist_id', backref='assessing_therapist', lazy=True)

#     # ADDED: Relationships for client-caregiver linking
#     # For a client, list of caregivers associated with them
#     caregivers_of_client = db.relationship(
#         'User', secondary=client_caregivers,
#         primaryjoin=(client_caregivers.c.client_id == id),
#         secondaryjoin=(client_caregivers.c.caregiver_id == id),
#         backref=db.backref('clients_managed', lazy='dynamic'),
#         lazy='dynamic'
#     )

#     def set_password(self, password):
#         self.password_hash = generate_password_hash(password)

#     def check_password(self, password):
#         return check_password_hash(self.password_hash, password)

#     def __repr__(self):
#         return f'<User {self.username} ({self.role})>'

# class Appointment(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     start_time = db.Column(db.DateTime, nullable=False)
#     end_time = db.Column(db.DateTime, nullable=False)
#     notes = db.Column(db.Text)
#     status = db.Column(db.String(20), default='scheduled') # 'scheduled', 'completed', 'cancelled'
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)

#     def __repr__(self):
#         return f'<Appointment {self.id} - Client: {self.client_id} - Therapist: {self.therapist_id}>'

# # MODIFIED: Renamed Message to UserMessage
# class UserMessage(db.Model):
#     __tablename__ = 'user_message' # ADDED: Explicit table name
#     id = db.Column(db.Integer, primary_key=True)
#     sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     content = db.Column(db.Text, nullable=False)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow)
#     is_read = db.Column(db.Boolean, default=False)

#     def __repr__(self):
#         return f'<UserMessage {self.id} - From: {self.sender_id} To: {self.receiver_id}>'

# class Alert(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     type = db.Column(db.String(50), nullable=False) # e.g., 'new_message', 'appointment_scheduled', 'patient_online'
#     message = db.Column(db.Text, nullable=False)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow)
#     is_read = db.Column(db.Boolean, default=False)

#     def __repr__(self):
#         return f'<Alert {self.id} - User: {self.user_id} - Type: {self.type}>'

# class PatientAssessment(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     form_type = db.Column(db.String(50), nullable=False) # 'outpatient', 'home_health'
#     form_data_json = db.Column(db.Text, nullable=False) # Store form data as JSON string
#     submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

#     def get_form_data(self):
#         return json.loads(self.form_data_json) if self.form_data_json else {}

#     def __repr__(self):
#         return f'<PatientAssessment {self.id} - Client: {self.client_id} - Type: {self.form_type}>'

# class Task(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Who assigned the task
#     title = db.Column(db.String(255), nullable=False)
#     description = db.Column(db.Text)
#     due_date = db.Column(db.DateTime)
#     status = db.Column(db.String(20), default='pending') # 'pending', 'completed', 'overdue'
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     completed_at = db.Column(db.DateTime, nullable=True)

#     def __repr__(self):
#         return f'<Task {self.id} - Client: {self.client_id} - Title: {self.title}>'




















# from datetime import datetime
# from flask_sqlalchemy import SQLAlchemy
# from flask_login import UserMixin
# from werkzeug.security import generate_password_hash, check_password_hash

# db = SQLAlchemy()

# # --- Database Models ---
# class User(db.Model, UserMixin):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80), unique=True, nullable=False)
#     email = db.Column(db.String(120), unique=True, nullable=False)
#     password_hash = db.Column(db.String(255), nullable=False)
#     name = db.Column(db.String(100), nullable=False)
#     role = db.Column(db.String(20), default='client', nullable=False) # 'admin', 'therapist', 'client'
#     is_online = db.Column(db.Boolean, default=False, nullable=False)
#     last_online = db.Column(db.DateTime, default=datetime.utcnow)

#     # Relationships
#     appointments_as_client = db.relationship('Appointment', foreign_keys='Appointment.client_id', backref='client', lazy=True, cascade="all, delete-orphan")
#     appointments_as_therapist = db.relationship('Appointment', foreign_keys='Appointment.therapist_id', backref='therapist', lazy=True, cascade="all, delete-orphan")
#     sent_messages = db.relationship('UserMessage', foreign_keys='UserMessage.sender_id', backref='sender', lazy=True, cascade="all, delete-orphan")
#     received_messages = db.relationship('UserMessage', foreign_keys='UserMessage.receiver_id', backref='receiver', lazy=True, cascade="all, delete-orphan")
#     alerts = db.relationship('Alert', backref='user', lazy=True, cascade="all, delete-orphan")
#     patient_assessments = db.relationship('PatientAssessment', foreign_keys='PatientAssessment.therapist_id', backref='therapist_user', lazy=True, cascade="all, delete-orphan")
#     # For clients, link to assessments they are part of (if needed)
#     client_assessments = db.relationship('PatientAssessment', foreign_keys='PatientAssessment.client_id', backref='client_user', lazy=True)


#     def set_password(self, password):
#         self.password_hash = generate_password_hash(password)

#     def check_password(self, password):
#         return check_password_hash(self.password_hash, password)

#     def __repr__(self):
#         return f'<User {self.username} ({self.role})>'

# class Appointment(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     start_time = db.Column(db.DateTime, nullable=False)
#     end_time = db.Column(db.DateTime, nullable=False)
#     notes = db.Column(db.Text, nullable=True)
#     status = db.Column(db.String(20), default='scheduled', nullable=False) # scheduled, completed, cancelled
#     reminder_sent = db.Column(db.Boolean, default=False, nullable=False)

#     def __repr__(self):
#         return f'<Appointment {self.id} for Client {self.client_id} with Therapist {self.therapist_id}>'

# class UserMessage(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     content = db.Column(db.Text, nullable=False)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
#     is_read = db.Column(db.Boolean, default=False, nullable=False)

#     def __repr__(self):
#         return f'<Message {self.id} from {self.sender_id} to {self.receiver_id}>'

# class Alert(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     type = db.Column(db.String(50), nullable=False) # e.g., 'appointment_reminder', 'patient_online', 'new_message'
#     message = db.Column(db.Text, nullable=False)
#     timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
#     is_read = db.Column(db.Boolean, default=False, nullable=False)

#     def __repr__(self):
#         return f'<Alert {self.id} for User {self.user_id} ({self.type})>'

# class PatientAssessment(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     therapist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     form_type = db.Column(db.String(50), nullable=False) # e.g., 'outpatient', 'home_health'
#     form_data_json = db.Column(db.Text, nullable=False) # Store form data as JSON string
#     date_completed = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

#     def __repr__(self):
#         return f'<Assessment {self.id} ({self.form_type}) by Therapist {self.therapist_id} for Client {self.client_id}>'

