import os


basedir = os.path.abspath(os.path.dirname(__file__))
class Config:
    # Secret key for Flask sessions and security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'atom_built_it'

    # Database configuration
    # Using SQLite for simplicity. The database file will be in the 'instance' folder.
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'gerio_care.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Mail configuration for sending emails
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 465)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = MAIL_USERNAME # Use the same email as sender by default

    # Flask-SocketIO configuration
    # For production, consider using a message queue like Redis
    # For local development, eventlet or gevent is fine
    SOCKETIO_MESSAGE_QUEUE = None # Set to 'redis://localhost:6379' for Redis in production

    # Application specific settings
    # Roles for users
    USER_ROLES = ['admin', 'therapist', 'client']
    
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads', 'tasks')
    THUMBNAIL_FOLDER = os.path.join(UPLOAD_FOLDER, 'thumbnails')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB max upload size
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'webm'}
    
    # NEW: Paystack Configuration
    PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY') or 'pk_test_45cac4a04f3c4004a98ddef5194bf87eaa2b9b9a' # Replace with your public key
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY') or 'sk_test_31de261eb78f6c3197d6702ecc3b6b662d819faf' # Replace with your secret key
    PAYSTACK_WEBHOOK_SECRET = os.environ.get('PAYSTACK_WEBHOOK_SECRET') or 'whsec_https://geriocare.onrender.com/ps_webhook' # Replace with your webhook secret

    # Application Version (optional, for display)
    APP_VERSION = "1.0.0" # You can update this as your app evolves