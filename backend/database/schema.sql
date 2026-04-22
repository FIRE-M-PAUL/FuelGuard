BEGIN TRANSACTION;
CREATE TABLE approval_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            requested_by INTEGER NOT NULL,
            approved_by INTEGER,
            request_date TIMESTAMP NOT NULL,
            decision_date TIMESTAMP,
            CHECK (status IN ('Pending', 'Approved', 'Rejected')),
            FOREIGN KEY(requested_by) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(approved_by) REFERENCES users(id) ON DELETE SET NULL
        );
CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
CREATE TABLE expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TIMESTAMP NOT NULL,
            recorded_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (amount > 0),
            FOREIGN KEY(recorded_by) REFERENCES users(id) ON DELETE RESTRICT
        );
CREATE TABLE fuel_purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL,
            fuel_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price_per_litre REAL NOT NULL,
            total_cost REAL NOT NULL,
            purchase_date TIMESTAMP NOT NULL,
            recorded_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (quantity > 0),
            CHECK (price_per_litre > 0),
            CHECK (total_cost > 0),
            FOREIGN KEY(recorded_by) REFERENCES users(id) ON DELETE RESTRICT
        );
CREATE TABLE fuel_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            driver_name TEXT NOT NULL,
            fuel_amount REAL NOT NULL,
            fuel_type TEXT NOT NULL,
            record_date TEXT NOT NULL,
            location TEXT NOT NULL,
            odometer_reading REAL NOT NULL,
            cost REAL NOT NULL,
            station_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_by INTEGER NOT NULL,
            reviewed_by INTEGER,
            review_note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (fuel_amount >= 0),
            CHECK (odometer_reading >= 0),
            CHECK (cost >= 0),
            CHECK (status IN ('pending', 'approved', 'rejected')),
            FOREIGN KEY(submitted_by) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL
        );
CREATE TABLE fuel_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuel_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price_per_litre REAL NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            vehicle_number TEXT NOT NULL,
            salesperson_id INTEGER NOT NULL,
            sale_date TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payment_verified INTEGER NOT NULL DEFAULT 0, verified_at TIMESTAMP, verified_by INTEGER,
            CHECK (quantity > 0),
            CHECK (price_per_litre > 0),
            CHECK (total_amount > 0),
            FOREIGN KEY(salesperson_id) REFERENCES users(id) ON DELETE RESTRICT
        );
CREATE TABLE fuel_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuel_type TEXT NOT NULL UNIQUE,
            available_litres REAL NOT NULL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP, minimum_level REAL NOT NULL DEFAULT 1200.0, selling_price_per_litre REAL NOT NULL DEFAULT 2.5,
            CHECK (available_litres >= 0)
        );
INSERT INTO "fuel_stock" VALUES(1,'Diesel',10000.0,'2026-04-22 05:25:42',1200.0,2.5);
INSERT INTO "fuel_stock" VALUES(2,'Petrol',10000.0,'2026-04-22 05:25:42',1200.0,2.5);
CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT,
            department TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (role IN ('sales', 'manager', 'accountant', 'admin')),
            CHECK (status IN ('active', 'inactive', 'pending'))
        );
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_fuel_status ON fuel_records(status);
CREATE INDEX idx_fuel_date ON fuel_records(record_date);
CREATE INDEX idx_fuel_submitted_by ON fuel_records(submitted_by);
CREATE INDEX idx_fuel_vehicle_id ON fuel_records(vehicle_id);
CREATE INDEX idx_fuel_sales_salesperson ON fuel_sales(salesperson_id);
CREATE INDEX idx_fuel_sales_sale_date ON fuel_sales(sale_date);
CREATE INDEX idx_expenses_date ON expenses(date);
CREATE INDEX idx_expenses_recorded ON expenses(recorded_by);
CREATE INDEX idx_purchases_date ON fuel_purchases(purchase_date);
CREATE INDEX idx_approval_status ON approval_requests(status);
CREATE INDEX idx_approval_requested_by ON approval_requests(requested_by);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('fuel_stock',2);
COMMIT;
