from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    residence = db.Column(db.String(100), nullable=False)
    class_name = db.Column(db.String(50), nullable=False)
    session = db.Column(db.String(50), nullable=False)
    payments = db.relationship('Payment', backref='student', lazy=True, cascade="all, delete-orphan")

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id', name='fk_payment_student'), nullable=False)
    transaction_number = db.Column(db.String(20), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_type = db.Column(db.String(50), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    qualification = db.Column(db.String(200))
    subject = db.Column(db.String(100))
    joining_date = db.Column(db.DateTime, default=datetime.utcnow)
    credentials_file = db.Column(db.String(200))

    __table_args__ = (
        db.UniqueConstraint('email', name='uq_teacher_email'),
    ) 