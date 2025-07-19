# GerioCare App

Developed by: **Atom De Legend**

---

## 📚 Table of Contents

- [About GerioCare](#1-about-geriocare)
- [Features](#2-features)
- [Technologies Used](#3-technologies-used)
- [Setup and Installation](#4-setup-and-installation)
- [Usage](#5-usage)
- [Project Structure](#6-project-structure)
- [License](#7-license)

---

## 1. About GerioCare

**GerioCare** is a comprehensive web application designed to streamline and enhance elderly care by connecting clients, therapists, and caregivers. It provides a centralized platform for managing personalized therapy tasks, appointments, assessments, and real-time communication, fostering a collaborative environment for holistic well-being.

The application also incorporates a **subscription model** to unlock premium features for clients.

---

## 2. Features

- **User Authentication & Roles**
  - Secure login/registration
  - Role-based access for Admins, Therapists, Clients, and Caregivers

- **Personalized Care Plans**
  - Therapists assign custom tasks with descriptions, images, or videos

- **Real-time Messaging**
  - In-app chat between therapists, clients, and caregivers

- **Appointment Management**
  - Schedule and view therapy sessions

- **Patient Assessments**
  - Outpatient and Home Health forms for therapist input

- **Progress Tracking**
  - Monitor task completion and client progress

- **Caregiver Linking**
  - Therapists/Admins assign caregivers to clients

- **Real-time Alerts**
  - Notifications for new messages, tasks, and appointments

- **Client Subscription Model**
  - Access core features with active plan
  - Pricing: Monthly, Quarterly, or Annual
  - Paystack integration for secure payments

- **Static Pages**
  - "About Us", "Contact", "Privacy Policy", "Terms of Use"

---

## 3. Technologies Used

### Backend:
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-Mail
- Flask-SocketIO
- SQLite (default, can switch to PostgreSQL/MySQL)
- Pillow (PIL)
- Requests
- hmac & hashlib
- python-dotenv
- Subprocess (for ffmpeg)

### Frontend:
- HTML5, CSS3, JavaScript
- Font Awesome
- Paystack Inline JS

### Development Tools:
- Python 3.8+
- pip
- venv
- FFmpeg (optional, for thumbnails)

---

## 4. Setup and Installation

### 🔧 Prerequisites
- Python 3.8+
- pip
- venv
- FFmpeg (optional): [Download FFmpeg](https://ffmpeg.org/download.html)

---

### 📥 Cloning the Repository
```bash
git clone <repository_url>
cd geriocare
```

---

### 🧪 Setting up the Virtual Environment
```bash
python -m venv venv
```

Activate it:

- On Windows:
  ```bash
  .\venv\Scripts\activate
  ```

- On macOS/Linux:
  ```bash
  source venv/bin/activate
  ```

---

### 📦 Installing Dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is missing:
```bash
pip install Flask Flask-SQLAlchemy Flask-Login Flask-Mail Flask-SocketIO python-dotenv Pillow requests
```

---

### ⚙️ Environment Variables

Create a `.env` file with:

```env
SECRET_KEY='your_very_secret_key_here_for_flask_sessions'
DATABASE_URL='sqlite:///instance/geriocare.db'

# Flask-Mail
MAIL_SERVER='smtp.gmail.com'
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME='your_email@example.com'
MAIL_PASSWORD='your_app_specific_password'

# Paystack
PAYSTACK_PUBLIC_KEY='pk_test_xxxxxxxxxxxxxxxxx'
PAYSTACK_SECRET_KEY='sk_test_xxxxxxxxxxxxxxxxx'
PAYSTACK_WEBHOOK_SECRET='your_webhook_secret_here'
```

> **Note**: Use an **app password** for Gmail if 2FA is enabled.

---

### 🗃️ Database Initialization

```bash
python app.py
```

- Creates `instance/geriocare.db`
- Initializes tables
- Default admin:
  - Username: `admin`
  - Password: `admin123`
- Adds default subscription plans

---

### ▶️ Running the Application

```bash
python app.py
```

Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 5. Usage

- Open your browser: `http://127.0.0.1:5000/`
- Login with admin credentials
- Register new users (Therapist, Client, Caregiver)
- Clients will be redirected to `/pricing` if not subscribed
- Purchase subscription via Paystack
- Explore the app's features!

---

## 6. Project Structure

```
geriocare/
├── app.py
├── config.py
├── models.py
├── .env
├── instance/
│   └── geriocare.db
├── static/
│   ├── css/
│   │   ├── base.css
│   │   ├── messages/messages.css
│   │   └── pages/
│   │       ├── landing_page.css
│   │       ├── my_subscription.css
│   │       ├── pricing_styles.css
│   │       └── static_content.css
│   ├── images/
│   └── js/
│       └── base.js
├── templates/
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── dashboards/
│   │   ├── admin_dashboard.html
│   │   ├── caregiver_dashboard.html
│   │   ├── client_dashboard.html
│   │   └── therapist_dashboard.html
│   ├── includes/footer.html
│   ├── appointments/appointments.html
│   ├── messages/messages.html
│   ├── forms/
│   │   ├── form_selection.html
│   │   ├── home_health_form.html
│   │   └── outpatient_form.html
│   ├── profile/profile_edit.html
│   ├── tasks/
│   │   ├── client_tasks.html
│   │   ├── caregiver_tasks.html
│   │   └── therapist_tasks.html
│   ├── users/
│   │   ├── link_caregiver.html
│   │   └── users_list.html
│   ├── assessments/assessments_list.html
│   ├── alerts/alerts_list.html
│   ├── 404.html
│   ├── 500.html
│   ├── about.html
│   ├── contact.html
│   ├── privacy_policy.html
│   ├── terms_of_use.html
│   ├── pricing.html
│   └── my_subscription.html
└── venv/
```

---

## 7. License

This project is open-source and available under the **MIT License**.

> You may add a `LICENSE` file to clarify usage rights.

---

🚀 Built with 💙 to enhance elderly care through technology.
