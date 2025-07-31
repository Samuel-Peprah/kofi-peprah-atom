# seed_db.py
import os
from app import app, db
from models import db, User, Plan  # Adjust if you use Blueprints or a package

def seed_plans():
    if Plan.query.count() == 0:
        print("Adding default subscription plans...")
        monthly_plan = Plan(
            name="Monthly Plan",
            amount_pesewas=5000,
            interval_days=30,
            description="Access to core features for one month."
        )
        quarterly_plan = Plan(
            name="Quarterly Plan",
            amount_pesewas=12000,
            interval_days=90,
            description="Extended access and additional features for three months."
        )
        annual_plan = Plan(
            name="Annual Plan",
            amount_pesewas=40000,
            interval_days=365,
            description="Full access to all premium features for one year with a discount."
        )
        db.session.add_all([monthly_plan, quarterly_plan, annual_plan])
        db.session.commit()
        print("✅ Plans added: Monthly, Quarterly, Annual.")
    else:
        print("✔️ Plans already exist. Skipping.")

def seed_users():
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
        print("✅ Admin user created: admin@geriocare.com / admin123")
    else:
        print("✔️ Admin user already exists. Skipping.")

if __name__ == "__main__":
    with app.app_context():
        if not os.path.exists(app.instance_path):
            os.makedirs(app.instance_path)

        db.create_all()
        seed_plans()
        seed_users()
        print("🎉 Seeding complete.")