from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime
import pandas as pd
import io
from models import db, Student, Payment, Teacher
import os
from werkzeug.utils import secure_filename
import random
import string
from sqlalchemy import or_, func, distinct
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure app
app.config.update(
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///academy.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv('SECRET_KEY', 'default-secret-key')
)

# Initialize extensions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

db.init_app(app)
migrate = Migrate(app, db)

# User model for login
class User(UserMixin):
    id = 1  # Static ID since we're using a predefined user

    @staticmethod
    def get(user_id):
        if user_id == 1:
            return User()
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'adminiyf':
            login_user(User())
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Get total number of students
    total_students = Student.query.count()

    # Get payment counts
    passport_count = db.session.query(func.count(distinct(Payment.student_id))).\
        filter(Payment.payment_type == 'Passport Fee').scalar() or 0
    
    graduation_count = db.session.query(func.count(distinct(Payment.student_id))).\
        filter(Payment.payment_type == 'Graduation Fee').scalar() or 0

    # Calculate total revenue
    total_revenue = db.session.query(func.sum(Payment.amount)).scalar() or 0

    # Get class distribution
    class_distribution = db.session.query(
        Student.class_name,
        func.count(Student.id)
    ).group_by(Student.class_name).all()

    class_labels = [c[0] for c in class_distribution]
    class_data = [c[1] for c in class_distribution]

    return render_template('index.html',
                         total_students=total_students,
                         passport_count=passport_count,
                         graduation_count=graduation_count,
                         total_revenue=total_revenue,
                         class_labels=class_labels,
                         class_data=class_data)

@app.route('/add_student', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        residence = request.form['residence']
        class_name = request.form['class']
        session = request.form['session']

        new_student = Student(name=name, phone=phone, residence=residence, class_name=class_name, session=session)
        db.session.add(new_student)
        db.session.commit()
        flash('Student added successfully', 'success')
        return redirect(url_for('index'))
    return render_template('add_student.html')

def generate_transaction_number():
    """Generate a unique transaction number"""
    prefix = 'TRX'
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}{random_chars}"

@app.route('/payments/<int:student_id>', methods=['GET', 'POST'])
@login_required
def manage_payments(student_id):
    student = Student.query.get_or_404(student_id)
    payments = Payment.query.filter_by(student_id=student_id).all()
    
    if request.method == 'POST':
        payment_type = request.form['payment_type']
        amount = request.form['amount']
        
        # Validate payment type
        if payment_type not in ['Passport Fee', 'Graduation Fee']:
            flash('Invalid payment type', 'error')
            return redirect(url_for('manage_payments', student_id=student_id))
        
        # Generate unique transaction number
        while True:
            transaction_number = generate_transaction_number()
            if not Payment.query.filter_by(transaction_number=transaction_number).first():
                break
            
        new_payment = Payment(
            student_id=student.id, 
            payment_type=payment_type, 
            amount=float(amount),
            transaction_number=transaction_number
        )
        db.session.add(new_payment)
        db.session.commit()
        flash('Payment added successfully', 'success')
        
        # Redirect to receipt page
        return redirect(url_for('view_receipt', payment_id=new_payment.id))
    
    return render_template('manage_payments.html', student=student, payments=payments)

@app.route('/receipt/<int:payment_id>')
@login_required
def view_receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    student = Student.query.get_or_404(payment.student_id)
    return render_template('receipt.html', payment=payment, student=student)

@app.route('/delete_payment/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()
    flash('Payment deleted successfully', 'success')
    return redirect(url_for('manage_payments', student_id=payment.student_id))

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    # Also delete all associated payments
    payments = Payment.query.filter_by(student_id=student_id).all()
    for payment in payments:
        db.session.delete(payment)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/download_report')
@login_required
def download_report():
    students = Student.query.all()
    data = []
    for student in students:
        payments = Payment.query.filter_by(student_id=student.id).all()
        total_payment = sum(payment.amount for payment in payments)
        passport_fee = sum(payment.amount for payment in payments if payment.payment_type.lower() == "passport fee")
        graduation_fee = sum(payment.amount for payment in payments if payment.payment_type.lower() == "graduation fee")
        data.append({
            'Student Name': student.name,
            'Phone': student.phone,
            'Residence': student.residence,
            'Class': student.class_name,
            'Session': student.session,
            'Total Payment': total_payment,
            'Passport Fee': passport_fee,
            'Graduation Fee': graduation_fee
        })
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Student Payments')
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name='student_payment_report.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/record_payment', methods=['GET', 'POST'])
@login_required
def record_payment():
    # Handle search functionality
    search_query = request.args.get('search')
    student = None
    
    if search_query:
        # Search for student by name (case-insensitive)
        student = Student.query.filter(Student.name.ilike(f'%{search_query}%')).first()
    
    return render_template('record_payment.html', student=student)

@app.route('/record_payment/<int:student_id>', methods=['POST'])
@login_required
def process_payment(student_id):
    student = Student.query.get_or_404(student_id)
    
    amount = request.form.get('amount')
    payment_type = request.form.get('payment_type')
    
    if not payment_type:
        flash('Payment type is required', 'error')
        return redirect(url_for('record_payment', search=student.name))
    
    if amount:
        try:
            amount = float(amount)
            # Generate unique transaction number
            while True:
                transaction_number = generate_transaction_number()
                if not Payment.query.filter_by(transaction_number=transaction_number).first():
                    break
              
            # Create new payment record
            payment = Payment(
                amount=amount,
                student_id=student.id,
                transaction_number=transaction_number,
                payment_type=payment_type,
                date=datetime.utcnow()
            )
            db.session.add(payment)
            db.session.commit()
            flash('Payment recorded successfully!', 'success')
            return redirect(url_for('view_receipt', payment_id=payment.id))
        except ValueError:
            flash('Invalid amount provided', 'error')
    
    return redirect(url_for('record_payment', search=student.name))

# Add this configuration
UPLOAD_FOLDER = 'static/uploads/credentials'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/teachers')
@login_required
def teachers():
    teachers = Teacher.query.all()
    return render_template('teachers.html', teachers=teachers)

@app.route('/add_teacher', methods=['GET', 'POST'])
@login_required
def add_teacher():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        qualification = request.form['qualification']
        subject = request.form['subject']
        
        teacher = Teacher(
            name=name,
            phone=phone,
            email=email,
            qualification=qualification,
            subject=subject
        )

        # Handle file upload
        if 'credentials' in request.files:
            file = request.files['credentials']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                teacher.credentials_file = filename

        db.session.add(teacher)
        db.session.commit()
        flash('Teacher added successfully!', 'success')
        return redirect(url_for('teachers'))

    return render_template('add_edit_teacher.html')

@app.route('/edit_teacher/<int:teacher_id>', methods=['GET', 'POST'])
@login_required
def edit_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    
    if request.method == 'POST':
        teacher.name = request.form['name']
        teacher.phone = request.form['phone']
        teacher.email = request.form['email']
        teacher.qualification = request.form['qualification']
        teacher.subject = request.form['subject']

        if 'credentials' in request.files:
            file = request.files['credentials']
            if file and allowed_file(file.filename):
                # Delete old file if it exists
                if teacher.credentials_file:
                    old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], teacher.credentials_file)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                teacher.credentials_file = filename

        db.session.commit()
        flash('Teacher updated successfully!', 'success')
        return redirect(url_for('teachers'))

    return render_template('add_edit_teacher.html', teacher=teacher)

@app.route('/delete_teacher/<int:teacher_id>', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    
    # Delete credentials file if it exists
    if teacher.credentials_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], teacher.credentials_file)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    db.session.delete(teacher)
    db.session.commit()
    flash('Teacher deleted successfully!', 'success')
    return redirect(url_for('teachers'))

@app.route('/view_teacher/<int:teacher_id>')
@login_required
def view_teacher(teacher_id):
    teacher = Teacher.query.get_or_404(teacher_id)
    return render_template('view_teacher.html', teacher=teacher)

@app.route('/search_students')
@login_required
def search_students():
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Number of results per page

    # Get search parameters
    name = request.args.get('name', '').strip()
    class_name = request.args.get('class', '').strip()
    session = request.args.get('session', '').strip()

    # Build query
    query = Student.query

    if name:
        query = query.filter(Student.name.ilike(f'%{name}%'))
    if class_name:
        query = query.filter(Student.class_name.ilike(f'%{class_name}%'))
    if session:
        query = query.filter(Student.session.ilike(f'%{session}%'))

    # Order by name
    query = query.order_by(Student.name)

    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    students = pagination.items

    return render_template('search_students.html', 
                         students=students, 
                         pagination=pagination,
                         min=min)

# Add route for editing students
@app.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
@login_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        student.name = request.form['name']
        student.phone = request.form['phone']
        student.residence = request.form['residence']
        student.class_name = request.form['class']
        student.session = request.form['session']
        
        db.session.commit()
        flash('Student updated successfully', 'success')
        return redirect(url_for('search_students'))
    
    return render_template('edit_student.html', student=student)

@app.route('/report')
@login_required
def report():
    # Get total number of students
    total_students = Student.query.count()

    # Get number of students who paid each fee type
    passport_fee_count = db.session.query(func.count(distinct(Payment.student_id))).\
        filter(Payment.payment_type == 'Passport Fee').scalar() or 0
    
    graduation_fee_count = db.session.query(func.count(distinct(Payment.student_id))).\
        filter(Payment.payment_type == 'Graduation Fee').scalar() or 0

    # Get class distribution
    class_distribution = db.session.query(
        Student.class_name,
        func.count(Student.id)
    ).group_by(Student.class_name).all()

    class_labels = [c[0] for c in class_distribution]
    class_data = [c[1] for c in class_distribution]

    return render_template('report.html',
                         total_students=total_students,
                         passport_fee_count=passport_fee_count,
                         graduation_fee_count=graduation_fee_count,
                         class_labels=class_labels,
                         class_data=class_data)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
