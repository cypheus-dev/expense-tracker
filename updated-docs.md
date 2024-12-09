# System Śledzenia Wydatków Firmowych - Dokumentacja Techniczna

## Spis treści
1. [Wprowadzenie](#wprowadzenie)
2. [Architektura systemu](#architektura-systemu)
3. [Modele danych](#modele-danych)
4. [Role użytkowników](#role-użytkowników)
5. [Funkcjonalności](#funkcjonalności)
6. [Interfejsy](#interfejsy)
7. [Bezpieczeństwo](#bezpieczeństwo)
8. [Deployment](#deployment)
9. [Rozwój projektu](#rozwój-projektu)

## Wprowadzenie

System Śledzenia Wydatków Firmowych to aplikacja webowa stworzona w technologii Flask, zaprojektowana do zarządzania wydatkami firmowymi w organizacji. Głównym celem systemu jest uporządkowanie procesu rejestracji i kontroli wydatków dokonywanych kartami firmowymi przez pracowników.

### Główne cechy systemu:
- Wieloużytkownikowy dostęp z różnymi poziomami uprawnień
- Śledzenie wydatków w różnych walutach (PLN, EUR)
- Zarządzanie kartami płatniczymi
- Kategoryzacja wydatków
- Załączanie dokumentów (faktury, paragony)
- Eksport danych do Excela
- System logowania aktywności
- Zaawansowane filtrowanie i sortowanie wydatków
- Pełna ochrona CSRF dla operacji modyfikujących dane

## Architektura systemu

### Stos technologiczny:
- **Backend**: Python 3.x + Flask
- **Baza danych**: PostgreSQL (production) / SQLite (development)
- **ORM**: SQLAlchemy
- **Frontend**: HTML + Bootstrap
- **Autentykacja**: Flask-Login
- **Bezpieczeństwo**: Flask-WTF (CSRF protection)
- **Hosting**: Render.com

### Struktura projektu:
```
expense-tracker/
├── app.py                 # Główny plik aplikacji
├── requirements.txt       # Zależności projektu
├── render.yaml           # Konfiguracja deploymentu
└── templates/            # Szablony HTML
    ├── base.html
    ├── index.html
    ├── login.html
    ├── add_expense.html
    ├── edit_expense.html
    ├── config.html
    ├── reports.html
    └── logs.html
```

### Konfiguracja aplikacji:
```python
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key')
```

## Modele danych

### User
- Reprezentuje użytkownika systemu
- Pola:
  - id: Integer (PK)
  - username: String (unikalne)
  - password_hash: String
  - role: String ('admin', 'accountant', 'user')
  - expenses: Relacja one-to-many z Expense

### Expense
- Reprezentuje pojedynczy wydatek
- Pola:
  - id: Integer (PK)
  - date: DateTime
  - amount: Float
  - currency: String (PLN/EUR)
  - description: String
  - card_id: Integer (FK)
  - user_id: Integer (FK)
  - receipt_data: LargeBinary
  - receipt_filename: String
  - status: String

### PaymentCard
- Reprezentuje kartę płatniczą
- Pola:
  - id: Integer (PK)
  - name: String
  - currency: String
  - description: String
  - is_active: Boolean
  - is_default: Boolean
  - expenses: Relacja one-to-many z Expense

### DeleteForm
- Formularz CSRF dla operacji usuwania
- Klasa:
  ```python
  class DeleteForm(FlaskForm):
      class Meta:
          csrf = True
  ```

## Bezpieczeństwo

### Autentykacja
- System logowania oparty o Flask-Login
- Hashowanie haseł (Werkzeug)
- Sesje użytkowników
- Wymagane logowanie dla wszystkich funkcji

### Autoryzacja
- System ról (admin, accountant, user)
- Sprawdzanie uprawnień przy każdym żądaniu
- Separacja danych między użytkownikami
- Bezpieczny dostęp do plików

### Zabezpieczenia CSRF
- Flask-WTF dla ochrony przed CSRF
- Tokeny CSRF dla wszystkich formularzy POST
- Walidacja tokenów przy modyfikacji danych
- Implementacja:
  ```python
  # Inicjalizacja
  csrf = CSRFProtect()
  csrf.init_app(app)
  
  # Użycie w widokach
  @app.route('/delete_expense/<int:expense_id>', methods=['POST'])
  @login_required
  def delete_expense(expense_id):
      form = DeleteForm()
      if not form.validate_on_submit():
          return jsonify({'error': 'Invalid CSRF token'}), 400
  ```

### Dodatkowe zabezpieczenia
- Walidacja danych wejściowych
- Limity wielkości przesyłanych plików
- Bezpieczne przechowywanie haseł

## Deployment

### Konfiguracja Render.com
- Typ: Web Service
- Środowisko: Python
- Plan bazy danych: PostgreSQL
- Zmienne środowiskowe:
  - FLASK_ENV
  - SECRET_KEY
  - DATABASE_URL

### Wymagania systemowe
- Python 3.x
- PostgreSQL
- Zależności z requirements.txt:
  ```
  Flask==2.2.5
  Flask-WTF==1.2.1
  Flask-SQLAlchemy==3.0.2
  SQLAlchemy==1.4.41
  Flask-Login==0.6.2
  gunicorn==20.1.0
  psycopg2-binary==2.9.6
  ```

## Rozwój projektu

### Planowane funkcjonalności
1. System powiadomień email
2. Integracja z systemami księgowymi
3. API do automatycznego importu transakcji
4. Rozszerzona analityka i raporty
5. Mobilny interfejs użytkownika

### Wytyczne rozwoju
1. Utrzymanie zgodności z PEP 8
2. Dokumentowanie nowych funkcji
3. Testowanie nowych funkcjonalności
4. Zachowanie istniejącej struktury uprawnień