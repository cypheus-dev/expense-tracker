from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO
from enum import Enum
import xlsxwriter
import os
import locale

# Ustawienie locale dla polskich nazw miesięcy
try:
    locale.setlocale(locale.LC_TIME, 'pl_PL.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Polish_Poland.1250')
    except:
        pass

app = Flask(__name__)

# Konfiguracja dla Render
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicjalizacja rozszerzeń
db = SQLAlchemy()
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Currency(Enum):
    PLN = "PLN"
    EUR = "EUR"
    
    @classmethod
    def choices(cls):
        return [(currency.value, currency.value) for currency in cls]

class PaymentCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='PLN')
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    expenses = db.relationship('Expense', backref='card', lazy=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin', 'accountant', 'user'
    expenses = db.relationship('Expense', backref='user', lazy=True)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_accountant(self):
        return self.role == 'admin' or self.role == 'accountant'

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, default=False)
    expenses = db.relationship('Expense', backref='category', lazy=True)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='PLN')
    description = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    card_id = db.Column(db.Integer, db.ForeignKey('payment_card.id'))
    receipt_data = db.Column(db.LargeBinary)
    receipt_filename = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')

    @property
    def status_color(self):
        return {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger'
        }.get(self.status, 'secondary')

@app.template_filter('month_name')
def month_name_filter(date_str):
    try:
        date = datetime.strptime(date_str, '%Y-%m')
        return date.strftime('%B %Y').capitalize()
    except:
        return date_str

@app.template_filter('sum_by_currency')
def sum_by_currency(expenses, currency):
    return sum(expense.amount for expense in expenses if expense.currency == currency)

@app.template_filter('format_currency')
def format_currency(amount, currency):
    if currency == 'PLN':
        return f"{amount:.2f} zł"
    elif currency == 'EUR':
        return f"{amount:.2f} €"
    return f"{amount:.2f}"

@app.template_filter('datetime')
def datetime_filter(value, format='%Y-%m-%d'):
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, format)
        except:
            return value
    return value
	
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Zwiększamy ilość wydatków na stronę ze względu na grupowanie
    
    if current_user.is_accountant:
        pagination = Expense.query.order_by(Expense.date.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
    else:
        pagination = Expense.query.filter_by(user_id=current_user.id)\
            .order_by(Expense.date.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
    
    # Zmieniamy sposób przekazywania danych do szablonu
    return render_template('index.html', 
                         pagination=pagination,
                         expenses=pagination.items)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Nieprawidłowe dane logowania', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    cards = PaymentCard.query.filter_by(is_active=True).all()
    categories = Category.query.all()
    if request.method == 'POST':
        try:
            expense = Expense(
                date=datetime.strptime(request.form['date'], '%Y-%m-%d'),
                amount=float(request.form['amount']),
                currency=request.form['currency'],
                description=request.form['description'],
                category_id=int(request.form['category']),
                card_id=int(request.form['card_id']),
                user_id=current_user.id
            )
            
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename:
                    if file.content_length and file.content_length > 5 * 1024 * 1024:
                        flash('Plik jest za duży. Maksymalny rozmiar to 5MB.', 'danger')
                        return redirect(request.url)
                    
                    expense.receipt_data = file.read()
                    expense.receipt_filename = file.filename
            
            db.session.add(expense)
            db.session.commit()
            flash('Wydatek został dodany pomyślnie.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Wystąpił błąd: {str(e)}', 'danger')
            return redirect(request.url)
            
    return render_template('add_expense.html', 
                         categories=categories,
                         cards=cards,
                         today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    if not current_user.is_accountant and expense.user_id != current_user.id:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))

    cards = PaymentCard.query.filter_by(is_active=True).all()
    categories = Category.query.all()
    
    if request.method == 'POST':
        try:
            expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
            expense.amount = float(request.form['amount'])
            expense.currency = request.form['currency']
            expense.description = request.form['description']
            expense.category_id = int(request.form['category'])
            expense.card_id = int(request.form['card_id'])
            
            if 'receipt' in request.files:
                file = request.files['receipt']
                if file and file.filename:
                    expense.receipt_data = file.read()
                    expense.receipt_filename = file.filename
            
            db.session.commit()
            flash('Wydatek został zaktualizowany.', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Wystąpił błąd: {str(e)}', 'danger')
    
    return render_template('edit_expense.html', 
                         expense=expense,
                         categories=categories,
                         cards=cards)

@app.route('/download_receipt/<int:expense_id>')
@login_required
def download_receipt(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if current_user.is_accountant or expense.user_id == current_user.id:
        if expense.receipt_data:
            return send_file(
                BytesIO(expense.receipt_data),
                download_name=expense.receipt_filename,
                as_attachment=True
            )
    flash('Brak dostępu lub brak pliku', 'danger')
    return redirect(url_for('index'))
	
@app.route('/reports')
@login_required
def reports():
    if not current_user.is_accountant:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))
    
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    
    # Total amounts by currency
    totals = db.session.query(
        Expense.currency,
        db.func.sum(Expense.amount).label('total')
    ).filter(
        Expense.date >= start_of_month
    ).group_by(
        Expense.currency
    ).all()
    
    total_by_currency = {t[0]: t[1] or 0 for t in totals}
    
    expense_count = Expense.query\
        .filter(Expense.date >= start_of_month).count()
    
    pending_count = Expense.query\
        .filter_by(status='pending').count()

    # Categories with currency split
    categories = db.session.query(
        Category.name,
        Expense.currency,
        db.func.sum(Expense.amount).label('total')
    ).join(Category)\
     .filter(Expense.date >= start_of_month)\
     .group_by(Category.name, Expense.currency)\
     .all()

    # Timeline with currency split
    timeline = db.session.query(
        db.func.date(Expense.date),
        Expense.currency,
        db.func.sum(Expense.amount).label('total')
    ).filter(
        Expense.date >= start_of_month
    ).group_by(
        db.func.date(Expense.date),
        Expense.currency
    ).order_by(
        db.func.date(Expense.date)
    ).all()

    return render_template('reports.html',
                         total_by_currency=total_by_currency,
                         expense_count=expense_count,
                         pending_count=pending_count,
                         categories=categories,
                         timeline=timeline)

@app.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if not current_user.is_admin:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        if 'add_user' in request.form:
            username = request.form.get('username')
            password = request.form.get('password')
            role = request.form.get('role', 'user')
            
            if User.query.filter_by(username=username).first():
                flash('Użytkownik o takiej nazwie już istnieje', 'danger')
            else:
                user = User(
                    username=username,
                    password_hash=generate_password_hash(password),
                    role=role
                )
                db.session.add(user)
                try:
                    db.session.commit()
                    flash('Użytkownik został dodany', 'success')
                except Exception as e:
                    db.session.rollback()
                    flash('Wystąpił błąd podczas dodawania użytkownika', 'danger')
    
    cards = PaymentCard.query.all()
    categories = Category.query.all()
    users = User.query.all()
    return render_template('config.html', 
                         cards=cards, 
                         categories=categories, 
                         users=users)

@app.route('/update_user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    if user_id == current_user.id:
        return jsonify({'error': 'Nie można edytować własnego konta'}), 400
        
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    try:
        if 'role' in data:
            user.role = data['role']
        if 'password' in data and data['password']:
            user.password_hash = generate_password_hash(data['password'])
            
        db.session.commit()
        return jsonify({'message': 'Zaktualizowano użytkownika'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    if user_id == current_user.id:
        return jsonify({'error': 'Nie można usunąć własnego konta'}), 400
        
    user = User.query.get_or_404(user_id)
    
    # Sprawdź czy użytkownik ma wydatki
    if user.expenses:
        return jsonify({'error': 'Nie można usunąć użytkownika, który ma wydatki'}), 400
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'message': 'Użytkownik został usunięty'})
	
@app.route('/config/card', methods=['POST'])
@login_required
def add_card():
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    name = request.form.get('name')
    currency = request.form.get('currency')
    description = request.form.get('description')
    
    card = PaymentCard(
        name=name,
        currency=currency,
        description=description
    )
    db.session.add(card)
    
    try:
        db.session.commit()
        flash('Karta została dodana', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas dodawania karty', 'danger')
    
    return redirect(url_for('config'))

@app.route('/config/card/<int:card_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_card(card_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    card = PaymentCard.query.get_or_404(card_id)
    
    if request.method == 'DELETE':
        if Expense.query.filter_by(card_id=card_id).first():
            return jsonify({'error': 'Nie można usunąć karty, która jest używana'}), 400
        db.session.delete(card)
    else:  # PUT
        data = request.get_json()
        card.name = data.get('name', card.name)
        card.currency = data.get('currency', card.currency)
        card.description = data.get('description', card.description)
        card.is_active = data.get('is_active', card.is_active)
    
    try:
        db.session.commit()
        return jsonify({'message': 'Operacja zakończona sukcesem'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/config/category', methods=['POST'])
@login_required
def add_category():
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    name = request.form.get('name')
    description = request.form.get('description')
    is_default = 'is_default' in request.form
    
    if is_default:
        # Usuń poprzednią domyślną kategorię
        Category.query.filter_by(is_default=True).update({'is_default': False})
    
    category = Category(
        name=name,
        description=description,
        is_default=is_default
    )
    db.session.add(category)
    
    try:
        db.session.commit()
        flash('Kategoria została dodana', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas dodawania kategorii', 'danger')
    
    return redirect(url_for('config'))

@app.route('/config/category/<int:category_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_category(category_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Brak uprawnień'}), 403
    
    category = Category.query.get_or_404(category_id)
    
    if request.method == 'DELETE':
        if Expense.query.filter_by(category_id=category_id).first():
            return jsonify({'error': 'Nie można usunąć kategorii, która jest używana'}), 400
        db.session.delete(category)
    else:  # PUT
        data = request.get_json()
        if data.get('is_default'):
            # Usuń poprzednią domyślną kategorię
            Category.query.filter_by(is_default=True).update({'is_default': False})
        category.name = data.get('name', category.name)
        category.description = data.get('description', category.description)
        category.is_default = data.get('is_default', category.is_default)
    
    try:
        db.session.commit()
        return jsonify({'message': 'Operacja zakończona sukcesem'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/export_expenses')
@login_required
def export_expenses():
    if not current_user.is_accountant:
        flash('Brak dostępu', 'danger')
        return redirect(url_for('index'))

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet()

    # Style
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#f0f0f0',
        'border': 1
    })
    
    date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
    amount_format_pln = workbook.add_format({'num_format': '#,##0.00 "zł"'})
    amount_format_eur = workbook.add_format({'num_format': '#,##0.00 "€"'})

    # Nagłówki
    headers = ['Data', 'Użytkownik', 'Karta', 'Kategoria', 'Opis', 'Kwota', 'Waluta', 'Status']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    # Dane
    expenses = Expense.query.order_by(Expense.date.desc()).all()
    for row, expense in enumerate(expenses, start=1):
        worksheet.write_datetime(row, 0, expense.date, date_format)
        worksheet.write(row, 1, expense.user.username)
        worksheet.write(row, 2, expense.card.name if expense.card else '')
        worksheet.write(row, 3, expense.category.name if expense.category else '')
        worksheet.write(row, 4, expense.description)
        if expense.currency == 'PLN':
            worksheet.write_number(row, 5, expense.amount, amount_format_pln)
        else:
            worksheet.write_number(row, 5, expense.amount, amount_format_eur)
        worksheet.write(row, 6, expense.currency)
        worksheet.write(row, 7, expense.status)

    # Autofiltr i szerokość kolumn
    worksheet.autofilter(0, 0, len(expenses), len(headers)-1)
    worksheet.set_column(0, 0, 12)  # Data
    worksheet.set_column(1, 1, 15)  # Użytkownik
    worksheet.set_column(2, 2, 15)  # Karta
    worksheet.set_column(3, 3, 15)  # Kategoria
    worksheet.set_column(4, 4, 40)  # Opis
    worksheet.set_column(5, 5, 12)  # Kwota
    worksheet.set_column(6, 6, 8)   # Waluta
    worksheet.set_column(7, 7, 10)  # Status

    # Podsumowanie
    summary_row = len(expenses) + 2
    worksheet.write(summary_row, 0, "Podsumowanie", header_format)
    
    # Suma PLN
    worksheet.write(summary_row, 1, "Suma PLN:")
    worksheet.write_formula(summary_row, 2, 
        f'=SUMIFS(F2:F{summary_row},G2:G{summary_row},"PLN")', 
        amount_format_pln)
    
    # Suma EUR
    worksheet.write(summary_row + 1, 1, "Suma EUR:")
    worksheet.write_formula(summary_row + 1, 2, 
        f'=SUMIFS(F2:F{summary_row},G2:G{summary_row},"EUR")', 
        amount_format_eur)

    workbook.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'wydatki_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

def init_app(app):
    with app.app_context():
        # Tworzenie tabel
        db.create_all()
        
        # Tworzenie domyślnego administratora
        if not User.query.filter_by(role='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash(os.environ.get('INITIAL_ADMIN_PASSWORD', 'Admin123!')),
                role='admin'
            )
            db.session.add(admin)
        
        # Tworzenie domyślnego księgowego
        if not User.query.filter_by(role='accountant').first():
            accountant = User(
                username='accountant',
                password_hash=generate_password_hash('Accountant123!'),
                role='accountant'
            )
            db.session.add(accountant)
            
        # Dodawanie domyślnych kategorii
        default_categories = [
            ("transport", "Wydatki na transport, paliwo, bilety", True),
            ("zakwaterowanie", "Hotele, noclegi", False),
            ("wyżywienie", "Posiłki, catering", False),
            ("materiały", "Materiały biurowe", False),
            ("inne", "Pozostałe wydatki", False)
        ]
        
        for name, description, is_default in default_categories:
            if not Category.query.filter_by(name=name).first():
                category = Category(name=name, description=description, is_default=is_default)
                db.session.add(category)

        # Dodawanie domyślnych kart
        default_cards = [
            ("Karta PLN", "PLN", "Karta złotówkowa"),
            ("Karta EUR", "EUR", "Karta euro")
        ]

        for name, currency, description in default_cards:
            if not PaymentCard.query.filter_by(name=name).first():
                card = PaymentCard(name=name, currency=currency, description=description)
                db.session.add(card)
        
        try:
            db.session.commit()
            print("Initialization completed successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error during initialization: {e}")

# Inicjalizacja przy starcie
with app.app_context():
    init_app(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
