import os
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from functools import wraps
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import platform
import csv
from io import StringIO
from flask_wtf.csrf import CSRFProtect, generate_csrf
# Load environment variables
load_dotenv()

# ========== APP CONFIGURATION ==========
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Initialize CSRF
csrf = CSRFProtect(app)
@app.after_request
def set_csrf_cookie(response):
    response.set_cookie('csrf_token', generate_csrf())
    return response

@app.before_request
def before_request():
    # Check if the request came from HTTP
    if request.headers.get('X-Forwarded-Proto') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, 301)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session security
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'  # HTTPS required in production
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.getenv('PERMANENT_SESSION_LIFETIME', 86400))
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # Add this – refreshes session on each request
# File upload configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 5 * 1024 * 1024))

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Configure Tesseract OCR path
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# Initialize database
db = SQLAlchemy(app)

# Initialize rate limiter

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    """Check if file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Always enable HSTS for HTTPS sites
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    # Disable caching - always fetch fresh content
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response
# ========== DATABASE MODELS ==========
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # Relationships
    expenses = db.relationship('Expense', backref='user', lazy=True)
    debts = db.relationship('Debt', backref='user', lazy=True)

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password,method='pbkdf2:sha256')

    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {'id': self.id, 'username': self.username}

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.String(200))
    date = db.Column(db.String(20))


    def to_dict(self):
        return {
            'id': self.id,
            'amount': self.amount,
            'category': self.category,
            'description': self.description,
            'date': self.date
        }

class Debt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    person_name = db.Column(db.String(100))
    amount = db.Column(db.Float)
    status = db.Column(db.String(20))
    debt_type = db.Column(db.String(20), default='owed_to_me')
    date_added = db.Column(db.String(20), default=datetime.now().strftime('%Y-%m-%d'))
    due_date = db.Column(db.String(20), default=None)
    description = db.Column(db.String(200), default='')
    category = db.Column(db.String(50), default='Other')
    notes = db.Column(db.Text, default='')

class UserCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='unique_user_category'),)

# Create all database tables
with app.app_context():
    db.create_all()
   # db.engine.execute("CREATE INDEX IF NOT EXISTS idx_expense_user_id ON expense (user_id)")
   # db.engine.execute("CREATE INDEX IF NOT EXISTS idx_expense_date ON expense (date)")
   # db.engine.execute("CREATE INDEX IF NOT EXISTS idx_debt_user_id ON debt (user_id)")

# ========== HELPER FUNCTIONS ==========

def get_auto_category(description):
    """Enhanced automatic categorization based on keywords"""
    if not description:
        return "Other"

    desc = description.lower()

    keywords = {
        'Food': ['lunch', 'dinner', 'breakfast', 'cafe', 'restaurant', 'food', 'meal', 'grocery', 'supermarket', 'coffee', 'snack', 'drink'],
        'Transport': ['taxi', 'bus', 'train', 'fuel', 'gas', 'transport', 'car', 'parking', 'flight', 'ride'],
        'Utilities': ['electricity', 'internet', 'wifi', 'bill', 'utility', 'phone', 'data', 'water bill', 'gas bill'],
        'Shopping': ['shop', 'store', 'mall', 'online', 'clothes', 'shoes', 'dress', 'electronics', 'phone', 'laptop', 'gadget', 'furniture', 'gift'],
        'Healthcare': ['hospital', 'doctor', 'medicine', 'clinic', 'pharmacy', 'health', 'medical', 'drug', 'appointment'],
        'Education': ['school', 'college', 'university', 'course', 'book', 'tuition', 'fee', 'class', 'training', 'education', 'exam'],
    }

    for category, tags in keywords.items():
        for tag in tags:
            if tag in desc:
                return category

    return "Other"

def get_smart_category(amount, description):
    """Smart categorization considering both description and amount"""
    category = get_auto_category(description)

    if amount > 10000 and category == "Other":
        return "Major Expense"
    elif amount < 50 and category == "Other":
        return "Miscellaneous"

    return category

def extract_transaction_details(image_path):
    """Smart OCR - Correctly extracts date from Payment Date & Time field"""
    try:
        # Open and preprocess image
        img = Image.open(image_path)
        img = img.convert('L')

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Apply sharpening
        img = img.filter(ImageFilter.SHARPEN)

        if img.width > 1000:
           img = img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
        else:
            img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
        # Extract text
        text = pytesseract.image_to_string(img)

        print("=" * 60)
        print("OCR EXTRACTED TEXT:")
        print(text if text else "[NO TEXT FOUND]")
        print("=" * 60)

        extracted_data = {
            'amount': 0.0,
            'date': None,  # Initialize as None instead of today to detect if date was found
            'description': '',
            'raw_text': text,
            'confidence': 'Low'
        }

        if not text or len(text.strip()) < 5:
            extracted_data['description'] = "Could not read image"
            return extracted_data

        # Remove commas from numbers
        text_clean = re.sub(r'(\d),(\d)', r'\1\2', text)

        # ========== FIND ALL NUMBERS WITH CONTEXT ==========
        number_matches = []
        for match in re.finditer(r'(\d+(?:\.\d{2})?)', text_clean):
            num_str = match.group(1)
            try:
                num_val = float(num_str)

                start = max(0, match.start() - 30)
                end = min(len(text_clean), match.end() + 30)
                context = text_clean[start:end]
                context_lower = context.lower()

                is_reference = False
                if len(num_str) >= 8 and '.' not in num_str:
                    is_reference = True
                if any(word in context_lower for word in ['ref', 'reference', 'invoice', 'receipt', 'no:', 'number', 'ft', 'txn']):
                    is_reference = True

                is_year = 1900 <= num_val <= 2030

                number_matches.append({
                    'value': num_val,
                    'context': context,
                    'is_reference': is_reference,
                    'is_year': is_year,
                    'has_decimal': '.' in num_str
                })
            except:
                continue

        print(f"\n🔢 NUMBERS FOUND:")
        for n in number_matches:
            print(f"   {n['value']} - Ref? {n['is_reference']} - Year? {n['is_year']}")

        # ========== FIND AMOUNT ==========
        amount_candidates = [n for n in number_matches if not n['is_reference'] and not n['is_year']]

        for candidate in amount_candidates:
            if re.search(r'ETB|Birr|birr|\$', candidate['context'], re.IGNORECASE):
                extracted_data['amount'] = candidate['value']
                print(f"✅ Amount from currency: {extracted_data['amount']}")
                break

        if extracted_data['amount'] == 0:
            decimal_amounts = [n for n in amount_candidates if n['has_decimal']]
            if decimal_amounts:
                extracted_data['amount'] = decimal_amounts[0]['value']
                print(f"✅ Amount with decimal: {extracted_data['amount']}")

        if extracted_data['amount'] == 0:
            reasonable = [n for n in amount_candidates if 5 <= n['value'] <= 100000]
            if reasonable:
                reasonable.sort(key=lambda x: x['value'])
                mid_idx = len(reasonable) // 2
                extracted_data['amount'] = reasonable[mid_idx]['value']
                print(f"✅ Amount from range: {extracted_data['amount']}")

        # ========== FIND DESCRIPTION ==========
        desc_patterns = [
            (r'Reason\s*/\s*Type of service[\s:]+([A-Za-z\s\.\-]{3,50})', 'reason'),
            (r'Receiver[\s:]+([A-Za-z\s\-]{3,50})', 'receiver'),
            (r'Payer[\s:]+([A-Za-z\s]+)', 'payer'),
            (r'for\s+([A-Za-z\s\.\-]{3,50})', 'for'),
            (r'to\s+([A-Za-z\s\.\-]{3,50})', 'to'),
        ]

        for pattern, field_name in desc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                desc = match.group(1).strip()
                if len(desc) > 3:
                    extracted_data['description'] = desc[:100]
                    print(f"✅ Description from {field_name}: {extracted_data['description']}")
                    break

        if not extracted_data['description']:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            bank_words = ['commercial', 'bank', 'receipt', 'customer', 'information',
                         'address', 'email', 'fax', 'thank', 'rights', 'reserved']
            for line in lines:
                line_lower = line.lower()
                if len(line) >= 5 and len(line) <= 100 and re.search(r'[A-Za-z]{3,}', line):
                    if not any(word in line_lower for word in bank_words):
                        extracted_data['description'] = line[:100]
                        print(f"✅ Description from line: {extracted_data['description']}")
                        break

        if not extracted_data['description']:
            extracted_data['description'] = "Transaction"

        # ========== FIND DATE - IMPROVED ==========
        # Priority 1: Look for "Payment Date & Time" field specifically
        date_match = re.search(r'Payment Date & Time[\s:]+([A-Za-z]+ \d{1,2},? \d{4})', text, re.IGNORECASE)
        if date_match:
            date_str = date_match.group(1)
            print(f"Found date string from Payment Date field: {date_str}")
            for fmt in ['%B %d, %Y', '%b %d, %Y', '%B %d %Y']:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    extracted_data['date'] = parsed_date.strftime('%Y-%m-%d')
                    print(f"✅ Date from Payment Date field: {extracted_data['date']}")
                    break
                except:
                    continue

        # Priority 2: Look for date near "May", "June", etc.
        if extracted_data['date'] is None:
            month_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})'
            month_match = re.search(month_pattern, text, re.IGNORECASE)
            if month_match:
                month = month_match.group(1)
                day = int(month_match.group(2))
                year = int(month_match.group(3))
                # Convert month name to number
                month_map = {
                    'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5, 'June': 6,
                    'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12,
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                month_num = month_map.get(month, 1)
                try:
                    extracted_data['date'] = datetime(year, month_num, day).strftime('%Y-%m-%d')
                    print(f"✅ Date from month pattern: {extracted_data['date']}")
                except:
                    pass

        # Priority 3: Look for common date patterns
        if extracted_data['date'] is None:
            date_patterns = [
                r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
                r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            ]
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    date_str = match.group(1)
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d']:
                        try:
                            parsed_date = datetime.strptime(date_str, fmt)
                            extracted_data['date'] = parsed_date.strftime('%Y-%m-%d')
                            print(f"✅ Date from pattern: {extracted_data['date']}")
                            break
                        except:
                            continue
                    if extracted_data['date'] is not None:
                        break

        # Fallback to today's date only if no date was extracted from screenshot
        if extracted_data['date'] is None:
            extracted_data['date'] = datetime.now().strftime('%Y-%m-%d')
            print(f"⚠️ No date found in screenshot, using today: {extracted_data['date']}")

        # Set confidence
        if extracted_data['amount'] > 0:
            extracted_data['confidence'] = 'High'

        print(f"\n📊 FINAL:")
        print(f"   💰 Amount: {extracted_data['amount']} ETB")
        print(f"   📝 Description: {extracted_data['description']}")
        print(f"   📅 Date: {extracted_data['date']}")

        return extracted_data

    except Exception as e:
        print(f"❌ OCR Error: {str(e)}")
        return {
            'amount': 0.0,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'description': 'OCR Scan Failed',
            'raw_text': '',
            'confidence': 'Low'
        }
# ========== DEBT MANAGEMENT HELPERS ==========

def is_debt_overdue(due_date):
    """Check if debt is overdue"""
    if not due_date:
        return False
    try:
        due = datetime.strptime(due_date, '%Y-%m-%d')
        return datetime.now() > due
    except:
        return False

def get_debt_statistics(user_id):
    """Get comprehensive debt statistics"""
    unpaid_owed_to_me = Debt.query.filter_by(user_id=user_id, status='Unpaid', debt_type='owed_to_me').all()
    unpaid_i_owe = Debt.query.filter_by(user_id=user_id, status='Unpaid', debt_type='i_owe').all()

    total_owed_to_me = sum(d.amount for d in unpaid_owed_to_me)
    total_i_owe = sum(d.amount for d in unpaid_i_owe)
    net_balance = total_owed_to_me - total_i_owe

    overdue_count = sum(1 for d in unpaid_owed_to_me + unpaid_i_owe if is_debt_overdue(d.due_date))

    return {
        'total_owed_to_me': total_owed_to_me,
        'total_i_owe': total_i_owe,
        'net_balance': net_balance,
        'overdue_count': overdue_count,
        'total_unpaid': len(unpaid_owed_to_me) + len(unpaid_i_owe)
    }

def get_debts_by_category(user_id):
    """Get debts grouped by category"""
    debts = Debt.query.filter_by(user_id=user_id, status='Unpaid').all()
    categories = {}
    for debt in debts:
        cat = debt.category or 'Other'
        if cat not in categories:
            categories[cat] = {'count': 0, 'amount': 0}
        categories[cat]['count'] += 1
        categories[cat]['amount'] += debt.amount
    return categories

# ========== TEMPLATE CONTEXT PROCESSORS ==========

@app.context_processor
def inject_now():
    """Make current datetime available to all templates"""
    return {'now': datetime.now()}

@app.context_processor
def inject_csrf():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)

@app.context_processor
def utility_processor():
    """Make helper functions available to all templates"""
    return {
        'get_auto_category': get_auto_category,
        'get_smart_category': get_smart_category
    }

# ========== PAGE ROUTES ==========

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@csrf.exempt
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        flash(' [Simulation Mode] A password reset link has been generated for your account.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/register', methods=['GET', 'POST'])
@csrf.exempt
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        confirm_password = request.form.get('confirm_password', '')

        # Validation checks
        errors = []

        # Check if username is empty
        if not username:
            errors.append("Username is required")

        # Check username length
        elif len(username) < 3:
            errors.append("Username must be at least 3 characters long")
        elif len(username) > 20:
            errors.append("Username must be less than 20 characters")

        # Check username characters (only letters, numbers, underscore)
        elif not re.match(r'^[A-Za-z0-9_]+$', username):
            errors.append("Username can only contain letters, numbers, and underscore")

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            errors.append("Username already exists")

        # Password validation
        if not password:
            errors.append("Password is required")
        elif len(password) < 6:
            errors.append("Password must be at least 6 characters long")
        elif len(password) > 50:
            errors.append("Password must be less than 50 characters")

        # Check password contains at least one letter and one number
        elif not re.search(r'[A-Za-z]', password):
            errors.append("Password must contain at least one letter")
        elif not re.search(r'\d', password):
            errors.append("Password must contain at least one number")

        # Check password confirmation
        if password != confirm_password:
            errors.append("Passwords do not match")

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html')

        # Create new user
        new_user = User(username=username)
        new_user.set_password(password)  # Hash password using set_password method
        db.session.add(new_user)
        db.session.commit()

        session.clear()
        session.permanent = True
        session['user_id'] = new_user.id
        session['username'] = new_user.username

        flash(f'✨ Welcome {username}! Your account has been created.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    expenses = Expense.query.filter_by(user_id=session['user_id']).all()
    cat_totals = {}
    for e in expenses:
        cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount
    total = sum(cat_totals.values())
    top_cat = max(cat_totals, key=cat_totals.get) if cat_totals else "None"
    category_distribution = []
    for cat, amount in cat_totals.items():
        percentage = (amount / total * 100) if total > 0 else 0
        category_distribution.append({
            'name': cat,
            'amount': amount,
            'percentage': round(percentage, 1)
        })
    category_distribution.sort(key=lambda x: x['amount'], reverse=True)

    # Monthly breakdown
    month_totals = {}
    for e in expenses:
        if e.date:
            try:
                month_key = datetime.strptime(e.date, '%Y-%m-%d').strftime('%b %Y')
                month_totals[month_key] = month_totals.get(month_key, 0) + e.amount
            except:
                continue

    # Sort months chronologically
    sorted_months = sorted(month_totals.keys(),
                          key=lambda x: datetime.strptime(x, '%b %Y'))

    return render_template('dashboard.html',
                           expenses=expenses,
                           category_labels=list(cat_totals.keys()),
                           category_values=list(cat_totals.values()),
                           month_labels=sorted_months,
                           month_values=[round(month_totals[m], 2) for m in sorted_months],
                           total_spent=round(total, 2),
                           average_spent=round(total/len(expenses), 2) if expenses else 0,
                           top_category=top_cat,
                           category_distribution=category_distribution)

@app.route('/transactions')
@login_required
def view_transactions():
    expenses = Expense.query.filter_by(user_id=session['user_id']).order_by(Expense.id.desc()).all()
    categories = list(set([e.category for e in expenses]))
    return render_template('transactions.html', expenses=expenses, category_labels=categories)

@app.route('/search')
@login_required
def search():
    search_type = request.args.get('type', '').strip()
    search_value = request.args.get('value', '').strip()

    # Validate search parameters
    if not search_type or search_type not in ['category', 'date']:
        flash('Invalid search type', 'warning')
        return redirect(url_for('view_transactions'))

    if not search_value:
        flash('Please enter a search value', 'warning')
        return redirect(url_for('view_transactions'))

    query = Expense.query.filter_by(user_id=session['user_id'])

    if search_type == 'category':
        # Validate category exists in user's expenses
        valid_categories = list(set([e.category for e in Expense.query.filter_by(user_id=session['user_id']).all()]))
        if search_value not in valid_categories:
            flash('Category not found in your expenses', 'warning')
            return redirect(url_for('view_transactions'))
        query = query.filter(Expense.category == search_value)
    elif search_type == 'date':
        # Validate date format (YYYY-MM-DD)
        try:
            datetime.strptime(search_value, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'warning')
            return redirect(url_for('view_transactions'))
        query = query.filter(Expense.date == search_value)

    expenses = query.order_by(Expense.date.desc()).all()

    user_expenses = Expense.query.filter_by(user_id=session['user_id']).all()
    categories = list(set([e.category for e in user_expenses]))
    dates = sorted(list(set([e.date for e in user_expenses])), reverse=True)

    return render_template('search.html',
                         expenses=expenses,
                         search_type=search_type,
                         search_value=search_value,
                         categories=categories,
                         dates=dates)

@app.route('/debts')
@login_required
def view_debts():
    owed_to_me = Debt.query.filter_by(user_id=session['user_id'], status='Unpaid', debt_type='owed_to_me').all()
    i_owe = Debt.query.filter_by(user_id=session['user_id'], status='Unpaid', debt_type='i_owe').all()
    paid_debts = Debt.query.filter_by(user_id=session['user_id'], status='Paid').all()

    total_owed_to_me = sum(debt.amount for debt in owed_to_me)
    total_i_owe = sum(debt.amount for debt in i_owe)
    net_balance = total_owed_to_me - total_i_owe

    stats = get_debt_statistics(session['user_id'])
    debts_by_category = get_debts_by_category(session['user_id'])

    for debt in owed_to_me + i_owe:
        debt.is_overdue = is_debt_overdue(debt.due_date)

    return render_template('debts.html',
                         owed_to_me=owed_to_me,
                         i_owe=i_owe,
                         paid_debts=paid_debts,
                         total_owed_to_me=total_owed_to_me,
                         total_i_owe=total_i_owe,
                         net_balance=net_balance,
                         debt_stats=stats,
                         debts_by_category=debts_by_category,
                         is_debt_overdue=is_debt_overdue)

@app.route('/add_expense_page')
@login_required
def add_expense_page():
    user_categories = UserCategory.query.filter_by(user_id=session['user_id']).all()
    return render_template('add_expense.html', user_categories=user_categories)


# ========== ACTION ROUTES ==========

@app.route('/add_expense', methods=['POST'])
@csrf.exempt
@login_required
def add_expense():
        # Timeout protection – prevent duplicate submissions
    last_submit = session.get('last_submit_time', 0)
    current_time = datetime.now().timestamp()

    if current_time - last_submit < 3:  # 3 seconds cooldown
        flash('⏳ Please wait – your expense is being saved...', 'warning')
        return redirect(url_for('view_transactions'))

    session['last_submit_time'] = current_time
    try:
        amount = float(request.form.get('amount', 0))
        description = request.form.get('description', '')
        date = request.form.get('date', datetime.now().strftime('%Y-%m-%d'))
        selected_category = request.form.get('category', 'Other')

        if selected_category == "Other" or selected_category is None or selected_category == '':
            category = get_smart_category(amount, description)
            auto_detected = True
        else:
            category = selected_category
            auto_detected = False

        new_ex = Expense(
            user_id=session['user_id'],
            amount=amount,
            description=description,
            category=category,
            date=date
        )
        db.session.add(new_ex)
        db.session.commit()

        if auto_detected:
            flash(f'✨ Expense added! Auto-categorized as: {category}', 'success')
        else:
            flash(f'✅ Expense added! Category: {category}', 'success')

    except Exception as e:
        print(f"ERROR adding expense: {str(e)}")
        flash(f'Error adding expense: {str(e)}', 'danger')

    return redirect(url_for('view_transactions'))

@app.route('/delete_expense/<int:id>', methods=['POST'])
@login_required
def delete_expense(id):
    ex = Expense.query.filter_by(id=id, user_id=session['user_id']).first()
    if ex:
        db.session.delete(ex)
        db.session.commit()
        flash('Expense deleted successfully!', 'success')
    return redirect(url_for('view_transactions'))

@app.route('/add_debt', methods=['POST'])
@csrf.exempt
@login_required
def add_debt():
    try:
        debt_type = request.form.get('debt_type', 'owed_to_me')
        category = request.form.get('category', 'Other')
        notes = request.form.get('notes', '')
        due_date = request.form.get('due_date', None) or None

        amount = float(request.form.get('amount', 0))
        if amount <= 0:
            flash('❌ Amount must be greater than zero.', 'danger')
            return redirect(url_for('view_debts'))

        new_d = Debt(
            user_id=session['user_id'],
            person_name=request.form.get('person_name'),
            amount=amount,
            status='Unpaid',
            debt_type=debt_type,
            description=request.form.get('description', ''),
            category=category,
            notes=notes,
            due_date=due_date
        )
        db.session.add(new_d)
        db.session.commit()

        if debt_type == 'owed_to_me':
            flash(f'✅ {request.form.get("person_name")} owes you ETB {amount}!', 'success')
        else:
            flash(f'✅ You owe {request.form.get("person_name")} ETB {amount}!', 'success')

    except Exception as e:
        flash(f'Error adding debt: {str(e)}', 'danger')

    return redirect(url_for('view_debts'))

@app.route('/export_data')
@login_required
def export_data():
    expenses = Expense.query.filter_by(user_id=session['user_id']).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Description', 'Category', 'Amount'])

    for expense in expenses:
        writer.writerow([expense.date, expense.description, expense.category, expense.amount])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=expenses.csv'
    response.headers['Content-type'] = 'text/csv'
    return response

@app.route('/toggle_debt/<int:id>', methods=['POST'])
@login_required
def toggle_debt(id):
    d = Debt.query.filter_by(id=id, user_id=session['user_id']).first()
    if d:
        d.status = 'Paid' if d.status == 'Unpaid' else 'Unpaid'
        db.session.commit()
        status_text = 'paid' if d.status == 'Paid' else 'marked as unpaid'
        flash(f'Debt {status_text}!', 'success')
    return redirect(url_for('view_debts'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ========== OCR ROUTES ==========
@app.route('/upload_ocr', methods=['POST'])
@login_required
def upload_ocr():
    if 'screenshot' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('add_expense_page'))

    file = request.files['screenshot']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('add_expense_page'))

    # ========== ADD THIS FILE VALIDATION HERE ==========
    if not allowed_file(file.filename):
        flash('File type not allowed. Please upload PNG, JPG, or JPEG', 'danger')
        return redirect(url_for('add_expense_page'))
    # ========== END OF ADDED CODE ==========

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        try:
            file.save(filepath)
            print(f"📁 File saved at: {filepath}")

            extracted = extract_transaction_details(filepath)
            print(f"🔍 OCR Result: {extracted}")

            session['ocr_temp'] = extracted

            if extracted['amount'] == 0:
                flash('⚠️ Could not detect amount clearly. Please check and enter manually.', 'warning')

            return render_template('ocr_confirm.html', extracted=extracted)

        except Exception as e:
            print(f"❌ OCR Exception: {str(e)}")
            flash(f'OCR failed: {str(e)}', 'danger')
            return redirect(url_for('add_expense_page'))

        finally:
            try:
                if os.path.exists(filepath):
                    import gc
                    gc.collect()
                    os.remove(filepath)
                    print(f"🗑️ Cleaned up file: {filepath}")
            except Exception as cleanup_error:
                print(f"⚠️ Could not delete file: {cleanup_error}")

    return redirect(url_for('add_expense_page'))

@app.route('/confirm_ocr', methods=['POST'])
@login_required
def confirm_ocr():
    if 'ocr_temp' not in session:
        flash('No OCR data found', 'danger')
        return redirect(url_for('add_expense_page'))

    ocr_data = session['ocr_temp']

    try:
        amount = float(request.form.get('amount', ocr_data.get('amount', 0)))
        description = request.form.get('description', ocr_data.get('description', 'OCR Scan'))
        date = request.form.get('date', ocr_data.get('date', datetime.now().strftime('%Y-%m-%d')))
        selected_category = request.form.get('category', 'Other')

        if selected_category == "Other" or selected_category is None or selected_category == '':
            category = get_smart_category(amount, description)
            auto_detected = True
        else:
            category = selected_category
            auto_detected = False

        if amount <= 0:
            flash('❌ Invalid amount extracted. Please try again with a clearer image.', 'danger')
            return redirect(url_for('add_expense_page'))

        new_expense = Expense(
            user_id=session['user_id'],
            amount=amount,
            description=description,
            category=category,
            date=date
        )
        db.session.add(new_expense)
        db.session.commit()

        session.pop('ocr_temp', None)

        if auto_detected:
            flash(f'✨ Expense added via OCR! Auto-categorized as: {category}', 'success')
        else:
            flash(f'✅ Expense added via OCR! Category: {category}', 'success')

    except Exception as e:
        print(f"OCR Confirm Error: {str(e)}")
        flash(f'Error saving expense: {str(e)}', 'danger')

    return redirect(url_for('view_transactions'))

# ========== ERROR HANDLERS ==========

@app.errorhandler(404)
def page_not_found(error):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('404.html'), 404
@app.errorhandler(500)
def internal_server_error(error):
    """Handle 500 - Internal server errors"""
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 - Forbidden errors"""
    return render_template('403.html'), 403

@app.route('/manifest.json')
def serve_manifest():
    response = send_from_directory('static', 'manifest.json')
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@app.route('/sw.js')
def serve_service_worker():
    response = send_from_directory('static', 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/add_category_ajax', methods=['POST'])
@login_required
def add_category_ajax():
    import json
    data = json.loads(request.data)
    category_name = data.get('category_name', '').strip()

    if not category_name or len(category_name) > 50:
        return {'success': False, 'error': 'Category name must be 1-50 characters'}

    existing = UserCategory.query.filter_by(user_id=session['user_id'], name=category_name).first()
    if existing:
        return {'success': False, 'error': 'Category already exists'}

    new_cat = UserCategory(user_id=session['user_id'], name=category_name)
    db.session.add(new_cat)
    db.session.commit()

    return {'success': True, 'category_name': category_name}

# ========== RUN THE APP ==========
if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV', 'development') == 'development'
    app.run(debug=debug_mode)
