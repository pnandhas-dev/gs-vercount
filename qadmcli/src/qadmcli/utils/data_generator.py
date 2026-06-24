"""Mockup data generator with intelligent field pattern recognition."""

import csv
import re
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class DataPattern:
    """Defines a data pattern for generating mock data."""
    
    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self.field_patterns: list[str] = []
        self.data_type_patterns: list[str] = []
    
    def matches(self, field_name: str, data_type: str) -> bool:
        """Check if this pattern matches the field."""
        field_upper = field_name.upper()
        data_type_upper = data_type.upper()
        
        # Check field name patterns
        for pattern in self.field_patterns:
            if pattern in field_upper:
                return True
        
        # Check data type patterns
        for pattern in self.data_type_patterns:
            if pattern in data_type_upper:
                return True
        
        return False
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> Any:
        """Generate mock data. Override in subclasses."""
        return None


class FirstNamePattern(DataPattern):
    """Generate first names."""
    
    FIRST_NAMES = [
        "John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Lisa",
        "William", "Mary", "James", "Patricia", "Thomas", "Linda", "Charles", "Barbara",
        "Daniel", "Elizabeth", "Matthew", "Jennifer", "Anthony", "Maria", "Mark", "Susan",
        "Donald", "Margaret", "Steven", "Dorothy", "Paul", "Jessica", "Andrew", "Nancy",
        "Joshua", "Karen", "Kenneth", "Betty", "Kevin", "Helen", "Brian", "Sandra",
        "George", "Donna", "Timothy", "Carol", "Ronald", "Ruth", "Edward", "Sharon",
        "Jason", "Michelle", "Jeffrey", "Laura", "Ryan", "Emma", "Jacob", "Olivia",
        "Gary", "Ava", "Nicholas", "Sophia", "Eric", "Isabella", "Jonathan", "Mia",
        "Stephen", "Charlotte", "Larry", "Amelia", "Justin", "Harper", "Scott", "Evelyn",
        "Brandon", "Abigail", "Benjamin", "Ella", "Samuel", "Chloe", "Gregory", "Victoria",
        "Frank", "Grace", "Alexander", "Zoey", "Raymond", "Nora", "Patrick", "Lily",
        "Jack", "Avery", "Dennis", "Eleanor", "Jerry", "Hannah", "Tyler", "Lillian",
        "Aaron", "Addison", "Jose", "Aubrey", "Adam", "Layla", "Nathan", "Brooklyn",
        "Henry", "Scarlett", "Douglas", "Zoe", "Zachary", "Leah", "Peter", "Hazel",
        "Kyle", "Violet", "Ethan", "Aurora", "Walter", "Savannah", "Noah", "Audrey"
    ]
    
    THAI_FIRST_NAMES = [
        "สมชาย", "สมหญิง", "ประเสริฐ", "มณี", "วิชัย", "พรทิพย์", "สุริยา", "กาญจนา",
        "นพดล", "วิภา", "ธีระ", "รัตนา", "อนุชา", "สุดา", "ประวิทย์", "จินตนา",
        "สุรศักดิ์", "อรทัย", "ยุทธนา", "พิศมัย", "ชัยวัฒน์", "บุษบา", "พงษ์ศักดิ์", "ลักขณา",
        "อำพล", "ขวัญใจ", "สมศักดิ์", "ดวงกมล", "บุญมี", "พรพิมล", "ประทีป", "สายฝน",
        "สมบัติ", "กัลยา", "สมหมาย", "นภสร", "สมาน", "กุลธิดา", "สมควร", "ปิยะพร",
        "สมพงษ์", "วิมล", "สมพร", "ธิดารัตน์", "สมบูรณ์", "อังคณา", "สมนึก", "ปรารถนา"
    ]
    
    def __init__(self):
        super().__init__("first_name", priority=100)
        self.field_patterns = [
            "FIRST_NAME", "FNAME", "FIRSTNAME", "GIVEN_NAME",
            "THAI_FIRST_NAME", "ENG_FIRST_NAME", "FIRST_NAME_TH", "FIRST_NAME_EN",
            "THAI_NAME", "NAME_THAI", "NAME_TH", "TH_NAME"  # Additional Thai patterns
        ]
        self.data_type_patterns = []
        self.thai_patterns = ["THAI", "TH_", "_TH", "NAME_THAI", "THAI_NAME"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None, 
                 field_name: str = "", ccsid: Optional[int] = None) -> str:
        # Check if Thai name field based on the actual field name
        field_upper = field_name.upper()
        is_thai = any(thai in field_upper for thai in self.thai_patterns)
        
        if is_thai:
            # DB2 for i automatically converts UTF-8 to the target CCSID
            # So we can always send Thai Unicode, regardless of CCSID
            # CCSID 838 (Thai EBCDIC), 1208 (UTF-8), etc. all accept Thai Unicode input
            return random.choice(self.THAI_FIRST_NAMES)
        
        return random.choice(self.FIRST_NAMES)


class LastNamePattern(DataPattern):
    """Generate last names."""
    
    LAST_NAMES = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
        "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas",
        "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
        "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
        "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
        "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
        "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
        "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
        "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
        "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
        "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza",
        "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers",
        "Long", "Ross", "Foster", "Jimenez", "Powell", "Jenkins", "Perry", "Russell"
    ]
    
    THAI_LAST_NAMES = [
        "แสงสว่าง", "รุ่งโรจน์", "วัฒนา", "พงษ์พิพัฒน์", "ศรีสุข", "ใจดี", "มั่นคง", "รักษาพล",
        "บุญยะ", "สมบูรณ์", "เกียรติศักดิ์", "ประดิษฐ์", "สุขุม", "วิริยะ", "อนุกูล", "สันติสุข",
        "พรหมมา", "จันทร์โอชา", "สุวรรณ", "แก้วกัลยา", "ทองดี", "บัวชุม", "รัตนมณี", "สมใจ",
        "ศิริพงษ์", "คำแสง", "นาคะ", "พิมพ์สวรรค์", "สุขเกษม", "มณีโชติ", "เทพทัต", "รอดคำ",
        "วงศ์ใหญ่", "ศรีเมือง", "บุญมี", "คงทน", "แก้วมา", "พรมบุตร", "สุขสม", "นามวงศ์"
    ]
    
    def __init__(self):
        super().__init__("last_name", priority=100)
        self.field_patterns = [
            "LAST_NAME", "LNAME", "LASTNAME", "SURNAME", "FAMILY_NAME",
            "THAI_LAST_NAME", "ENG_LAST_NAME", "LAST_NAME_TH", "LAST_NAME_EN",
            "THAI_SURNAME", "SURNAME_THAI"  # Additional Thai patterns
        ]
        self.thai_patterns = ["THAI", "TH_", "_TH", "THAI_SURNAME", "SURNAME_THAI"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None,
                 field_name: str = "", ccsid: Optional[int] = None) -> str:
        field_upper = field_name.upper()
        is_thai = any(thai in field_upper for thai in self.thai_patterns)
        
        if is_thai:
            # DB2 for i automatically converts UTF-8 to the target CCSID
            # So we can always send Thai Unicode, regardless of CCSID
            return random.choice(self.THAI_LAST_NAMES)
        
        return random.choice(self.LAST_NAMES)


class EmailPattern(DataPattern):
    """Generate email addresses."""
    
    DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "company.com", "example.com"]
    
    def __init__(self):
        super().__init__("email", priority=100)
        self.field_patterns = ["EMAIL", "E_MAIL", "MAIL"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> str:
        user = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 12)))
        domain = random.choice(self.DOMAINS)
        return f"{user}@{domain}"


class PhonePattern(DataPattern):
    """Generate phone numbers."""
    
    def __init__(self):
        super().__init__("phone", priority=100)
        self.field_patterns = [
            "PHONE", "MOBILE", "TEL", "CELL", "FAX",
            "MOBILE_NO", "PHONE_NO", "TEL_NO"
        ]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> str:
        # Generate Thai mobile format (10 digits starting with 0)
        if length == 10:
            prefixes = ["081", "082", "083", "084", "085", "086", "087", "088", "089", "090", "091", "092", "093", "094", "095", "096", "097", "098", "099"]
            prefix = random.choice(prefixes)
            suffix = ''.join(random.choices(string.digits, k=7))
            return f"{prefix}{suffix}"
        return ''.join(random.choices(string.digits, k=length or 10))


class CreditCardPattern(DataPattern):
    """Generate credit card-like numbers (16 digits with Luhn algorithm)."""
    
    def __init__(self):
        super().__init__("credit_card", priority=100)
        self.field_patterns = [
            "CREDIT_CARD", "CREDITCARD", "CC_NUMBER", "CC_NO", "CARD_NUMBER",
            "CARD_NO", "PAYMENT_CARD", "CCN", "CREDIT_CARD_NO"
        ]
    
    def _luhn_checksum(self, number: str) -> int:
        """Calculate Luhn checksum for a number."""
        def digits_of(n):
            return [int(d) for d in str(n)]
        
        digits = digits_of(number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        return checksum % 10
    
    def generate_luhn_number(self, length: int = 16) -> str:
        """Generate a Luhn-valid number (credit card format)."""
        # Generate length-1 random digits
        number = ''.join(random.choices(string.digits, k=length - 1))
        
        # Calculate check digit
        checksum = self._luhn_checksum(number + '0')
        check_digit = (10 - checksum) % 10
        
        return number + str(check_digit)
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> str:
        # Default to 16 digits for credit cards
        card_length = length if length else 16
        
        # Generate Luhn-valid number
        return self.generate_luhn_number(card_length)


class DatePattern(DataPattern):
    """Generate dates."""
    
    def __init__(self):
        super().__init__("date", priority=90)
        self.field_patterns = [
            "DATE", "CREATED_DATE", "UPDATED_DATE", "BIRTH_DATE", "DOB",
            "ORDER_DATE", "EFFECTIVE_DATE", "LAST_LOGIN_DATE"
        ]
        self.data_type_patterns = ["DATE", "TIMESTAMP", "TIMESTMP"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> datetime:
        # Generate random date within last 2 years
        days_back = random.randint(0, 730)
        return datetime.now() - timedelta(days=days_back)


class AmountPattern(DataPattern):
    """Generate monetary amounts."""
    
    def __init__(self):
        super().__init__("amount", priority=90)
        self.field_patterns = [
            "AMOUNT", "PRICE", "COST", "FEE", "TAX", "TOTAL", "BALANCE",
            "ORDER_AMOUNT", "UNIT_PRICE", "FEE_AMOUNT", "TAX_AMOUNT"
        ]
        self.data_type_patterns = ["DECIMAL", "NUMERIC"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None):
        # Generate reasonable amounts respecting DECIMAL precision
        # length = total digits, scale = decimal places
        
        if length and scale is not None:
            # Calculate max integer part based on precision
            max_int_digits = length - scale
            if max_int_digits > 0:
                max_int_val = (10 ** max_int_digits) - 1
                min_val = 1
                int_part = random.randint(min_val, max(1, max_int_val))
                dec_part = random.randint(0, (10 ** scale) - 1)
                value = int_part + (dec_part / (10 ** scale))
            else:
                # No integer digits, just decimal part (0.xxx)
                dec_part = random.randint(0, (10 ** scale) - 1)
                value = dec_part / (10 ** scale)
        else:
            # Fallback: generate reasonable amounts
            max_digits = min(length or 10, 12)  # Cap at 12 digits for safety
            max_val = 10 ** max_digits
            min_val = 10
            value = random.uniform(min_val, max_val)
        
        # Use provided scale or default to 2 decimal places
        decimal_places = scale if scale is not None else 2
        rounded_value = round(value, decimal_places)
        
        # Return as Decimal for proper DB2 DECIMAL compatibility
        from decimal import Decimal
        return Decimal(str(rounded_value))


class IDPattern(DataPattern):
    """Generate ID numbers."""
    
    def __init__(self):
        super().__init__("id", priority=95)
        self.field_patterns = [
            "ID", "CUST_ID", "USER_ID", "EMP_ID", "ORDER_ID", "SUBS_ID",
            "CUSTOMER_ID", "PRODUCT_ID", "TRANSACTION_ID"
        ]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> int:
        # Generate sequential-like IDs
        return random.randint(100000, 999999999)


class StatusPattern(DataPattern):
    """Generate status codes."""
    
    STATUSES = {
        "STATUS": ["A", "I", "P", "D"],  # Active, Inactive, Pending, Deleted
        "ORDER_STATUS": ["PE", "CF", "AL", "CA"],  # Pending, Confirmed, Allocated, Cancelled
        "TYPE": ["SI", "RE", "SW"],  # Subscribe, Redeem, Switch
    }
    
    def __init__(self):
        super().__init__("status", priority=80)
        self.field_patterns = ["STATUS", "TYPE", "STATE", "CODE"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> str:
        # Try to match specific status patterns
        for key, values in self.STATUSES.items():
            return random.choice(values)
        return random.choice(["A", "I", "P"])


class StringPattern(DataPattern):
    """Generate random strings as fallback."""
    
    def __init__(self):
        super().__init__("string", priority=10)
        self.field_patterns = ["NAME", "DESC", "TEXT", "REMARKS", "NOTE"]
        self.data_type_patterns = ["CHAR", "VARCHAR"]
    
    def generate(self, length: Optional[int] = None, scale: Optional[int] = None) -> str:
        max_len = min(length or 50, 100)
        min_len = min(5, max_len)  # Ensure min_len doesn't exceed max_len
        return ''.join(random.choices(string.ascii_letters + ' ', k=random.randint(min_len, max_len)))


class FileBasedDataSource:
    """Data source that loads data from a CSV file."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data: dict[str, list[str]] = {}
        self._load_data()

    def _load_data(self):
        """Load data from CSV file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Data file not found: {self.file_path}")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for column, value in row.items():
                    col_upper = column.upper().strip()
                    if col_upper not in self.data:
                        self.data[col_upper] = []
                    if value:
                        self.data[col_upper].append(value.strip())

    def get_value(self, column: str, index: Optional[int] = None) -> str:
        """Get a random value from the specified column."""
        col_upper = column.upper().strip()
        if col_upper not in self.data or not self.data[col_upper]:
            return ""

        values = self.data[col_upper]
        if index is not None and 0 <= index < len(values):
            return values[index]
        return random.choice(values)

    def get_paired_values(self, columns: list[str], index: Optional[int] = None) -> dict[str, str]:
        """Get paired values from multiple columns at the same row index."""
        result = {}

        # Find the minimum length across all columns
        min_length = float('inf')
        for col in columns:
            col_upper = col.upper().strip()
            if col_upper in self.data:
                min_length = min(min_length, len(self.data[col_upper]))
            else:
                min_length = 0
                break

        if min_length == 0:
            # Return empty values if any column is missing
            for col in columns:
                result[col] = ""
            return result

        # Use the same index for all columns to maintain pairing
        if index is None:
            index = random.randint(0, min_length - 1)
        else:
            index = index % min_length

        for col in columns:
            col_upper = col.upper().strip()
            result[col] = self.data[col_upper][index]

        return result

    def get_column_names(self) -> list[str]:
        """Get list of available column names."""
        return list(self.data.keys())


class DataGenerator:
    """Main data generator that selects appropriate patterns."""

    def __init__(self):
        self.patterns: list[DataPattern] = [
            FirstNamePattern(),
            LastNamePattern(),
            EmailPattern(),
            PhonePattern(),
            CreditCardPattern(),
            DatePattern(),
            AmountPattern(),
            IDPattern(),
            StatusPattern(),
            StringPattern(),
        ]
        # Sort by priority (highest first)
        self.patterns.sort(key=lambda p: p.priority, reverse=True)
        # File-based data sources cache
        self._file_sources: dict[str, FileBasedDataSource] = {}
        # Track paired column indices for consistent row selection
        self._paired_indices: dict[str, int] = {}
    
    def detect_pattern(self, column_name: str, data_type: str,
                        hint: Optional[str] = None) -> str:
        """Detect which pattern will be used for a column without generating data.
        
        Returns the pattern name that would be used for data generation.
        """
        # Check for hint first - it overrides automatic detection
        if hint:
            hint_lower = hint.lower().strip()
            if hint_lower:
                return f"hint:{hint_lower}"
        
        # Find matching pattern
        for pattern in self.patterns:
            if pattern.matches(column_name, data_type):
                return pattern.name
        
        # Fallback based on data type
        return self._fallback_pattern_name(data_type)
    
    def _fallback_pattern_name(self, data_type: str) -> str:
        """Get pattern name for fallback based on data type."""
        type_upper = data_type.upper()
        if "CHAR" in type_upper or "GRAPHIC" in type_upper:
            # Check if it's "FOR BIT DATA" (binary)
            if "FOR BIT DATA" in type_upper:
                return "binary"
            return "string"
        elif "INT" in type_upper or "SMALLINT" in type_upper:
            return "integer"
        elif "DECIMAL" in type_upper or "NUMERIC" in type_upper or "FLOAT" in type_upper:
            return "decimal"
        elif "DATE" in type_upper or "TIME" in type_upper or "TIMESTMP" in type_upper:
            return "datetime"
        elif "BLOB" in type_upper or "BINARY" in type_upper or "FOR BIT DATA" in type_upper:
            return "binary"
        else:
            return "default"
    
    def generate_for_column(self, column_name: str, data_type: str, 
                           length: Optional[int] = None, 
                           scale: Optional[int] = None,
                           hint: Optional[str] = None,
                           ccsid: Optional[int] = None) -> Any:
        """Generate mock data for a column based on its name and type.
        
        Supported hints:
        - first_name, last_name, full_name
        - thai_first_name, thai_last_name, thai_full_name
        - email
        - phone, mobile
        - credit_card, creditcard, cc_number
        - date, datetime, timestamp
        - amount, price, fee, tax
        - id, uuid
        - status, type, code
        - address, city, country
        - company, department
        - text, description, notes
        - random, uuid, hash
        - constant:<value> - Use a constant value
        - range:<min>:<max> - Numeric range
        - choices:<val1>,<val2>,<val3> - Random from choices
        
        CCSID handling:
        - CCSID 838: Thai EBCDIC - DB2 auto-converts UTF-8 to Thai EBCDIC
        - CCSID 1208: UTF-8 - Store as UTF-8
        - CCSID 65535: Binary - Generate hex string for binary data
        """
        
        # Check for hint first - it overrides automatic detection
        if hint:
            hint_lower = hint.lower().strip()
            result = self._generate_from_hint(hint_lower, length, scale, column_name, ccsid)
            if result is not None:
                return result
        
        # Special handling for CCSID 65535 (binary columns)
        if ccsid == 65535:
            # Generate hex string for binary data
            import string
            hex_length = min(length or 20, 64)
            return ''.join(random.choices(string.hexdigits.upper(), k=hex_length))
        
        # Find matching pattern
        for pattern in self.patterns:
            if pattern.matches(column_name, data_type):
                # Pass field_name for patterns that need it (like Thai name detection)
                try:
                    return pattern.generate(length, scale, field_name=column_name, ccsid=ccsid)
                except TypeError:
                    # Pattern doesn't accept field_name parameter
                    return pattern.generate(length, scale)
        
        # Fallback based on data type
        return self._fallback_generate(data_type, length, scale)
    
    def _generate_from_hint(self, hint: str, length: Optional[int], 
                           scale: Optional[int], field_name: str) -> Any:
        """Generate data based on explicit hint."""
        import uuid
        
        # Name patterns
        if hint == "first_name":
            return random.choice(FirstNamePattern.FIRST_NAMES)
        elif hint == "last_name":
            return random.choice(LastNamePattern.LAST_NAMES)
        elif hint == "full_name":
            return f"{random.choice(FirstNamePattern.FIRST_NAMES)} {random.choice(LastNamePattern.LAST_NAMES)}"
        elif hint == "thai_first_name":
            return random.choice(FirstNamePattern.THAI_FIRST_NAMES)
        elif hint == "thai_last_name":
            return random.choice(LastNamePattern.THAI_LAST_NAMES)
        elif hint == "thai_full_name":
            return f"{random.choice(FirstNamePattern.THAI_FIRST_NAMES)} {random.choice(LastNamePattern.THAI_LAST_NAMES)}"
        
        # Contact patterns
        elif hint == "email":
            return EmailPattern().generate(length, scale)
        elif hint == "phone" or hint == "mobile":
            prefixes = ["081", "082", "083", "084", "085", "086", "087", "088", "089", "090", "091", "092", "093", "094", "095", "096", "097", "098", "099"]
            prefix = random.choice(prefixes)
            suffix = ''.join(random.choices(string.digits, k=7))
            return f"{prefix}{suffix}"
        
        # Credit card pattern
        elif hint == "credit_card":
            cc_pattern = CreditCardPattern()
            return cc_pattern.generate(length or 16)
        
        # Date patterns
        elif hint in ["date", "datetime", "timestamp"]:
            days_back = random.randint(0, 730)
            return datetime.now() - timedelta(days=days_back)
        
        # Financial patterns
        elif hint in ["amount", "price", "fee", "tax", "balance"]:
            min_val = 10
            max_val = 10 ** (length or 6)
            value = random.uniform(min_val, max_val)
            return round(value, scale or 2)
        
        # ID patterns
        elif hint == "id":
            return random.randint(100000, 999999999)
        elif hint == "uuid":
            return str(uuid.uuid4())[:length] if length else str(uuid.uuid4())
        
        # Status/Type patterns
        elif hint in ["status", "type", "code"]:
            return random.choice(["A", "I", "P", "D", "Y", "N", "1", "0"])
        
        # Address patterns
        elif hint == "address":
            numbers = ''.join(random.choices(string.digits, k=3))
            streets = ["Main St", "High St", "Park Ave", "Broadway", "Elm St", "Maple Ave"]
            return f"{numbers} {random.choice(streets)}"
        elif hint == "city":
            cities = ["Bangkok", "New York", "London", "Tokyo", "Singapore", "Hong Kong"]
            return random.choice(cities)
        elif hint == "country":
            countries = ["TH", "US", "UK", "JP", "SG", "HK", "CN", "AU"]
            return random.choice(countries)
        
        # Company patterns
        elif hint == "company":
            prefixes = ["Global", "Advanced", "Prime", "United", "Tech", "Asia"]
            suffixes = ["Corp", "Ltd", "Inc", "Co", "Group", "Solutions"]
            return f"{random.choice(prefixes)} {random.choice(suffixes)}"
        elif hint == "department":
            depts = ["IT", "Sales", "Marketing", "HR", "Finance", "Operations"]
            return random.choice(depts)
        
        # Text patterns
        elif hint in ["text", "description", "notes", "remarks"]:
            max_len = min(length or 100, 200)
            words = ["Lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit"]
            return ' '.join(random.choices(words, k=random.randint(3, 10)))[:max_len]
        
        # Random patterns
        elif hint == "random":
            return ''.join(random.choices(string.ascii_letters + string.digits, k=length or 10))
        elif hint == "hash":
            return ''.join(random.choices(string.hexdigits, k=length or 32))
        
        # Constant value: constant:<value>
        elif hint.startswith("constant:"):
            return hint[9:]  # Return the constant value after "constant:"
        
        # Range: range:<min>:<max>
        elif hint.startswith("range:"):
            parts = hint.split(":")
            if len(parts) == 3:
                try:
                    min_val = int(parts[1])
                    max_val = int(parts[2])
                    return random.randint(min_val, max_val)
                except ValueError:
                    pass
        
        # Choices: choices:<val1>,<val2>,<val3>
        elif hint.startswith("choices:"):
            choices = hint[8:].split(",")
            return random.choice(choices) if choices else ""

        # File-based data: file:<path>:<column>
        # Example: file:/app/config/data/funds.csv:FUND_NAME_TH
        elif hint.startswith("file:"):
            parts = hint.split(":")
            if len(parts) >= 3:
                file_path = ":".join(parts[1:-1])  # Handle paths with colons
                column_name = parts[-1]
                return self._generate_from_file(file_path, column_name, field_name)

        # Paired file-based data: paired:<path>:<col1>,<col2>,...
        # Example: paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH
        elif hint.startswith("paired:"):
            parts = hint.split(":")
            if len(parts) >= 3:
                file_path = ":".join(parts[1:-1])
                columns = parts[-1].split(",")
                return self._generate_paired_from_file(file_path, columns, field_name)

        # Unknown hint - return None to fall back to automatic detection
        return None

    def _generate_from_file(self, file_path: str, column: str, field_name: str) -> str:
        """Generate data from a file-based source."""
        try:
            # Cache the file source
            if file_path not in self._file_sources:
                self._file_sources[file_path] = FileBasedDataSource(file_path)

            source = self._file_sources[file_path]
            return source.get_value(column)
        except Exception as e:
            # Fallback to empty string if file reading fails
            return ""

    def _generate_paired_from_file(self, file_path: str, columns: list[str], field_name: str) -> str:
        """Generate paired data from a file-based source.

        Uses the same row index for all columns in the pair group to maintain consistency.
        """
        try:
            # Cache the file source
            if file_path not in self._file_sources:
                self._file_sources[file_path] = FileBasedDataSource(file_path)

            source = self._file_sources[file_path]

            # Create a pair key based on file and columns
            pair_key = f"{file_path}:{','.join(columns)}"

            # Get or create a consistent index for this pair
            if pair_key not in self._paired_indices:
                # Find minimum length across all columns
                min_length = float('inf')
                for col in columns:
                    col_upper = col.upper().strip()
                    if col_upper in source.data:
                        min_length = min(min_length, len(source.data[col_upper]))
                    else:
                        min_length = 0
                        break

                if min_length > 0:
                    self._paired_indices[pair_key] = random.randint(0, min_length - 1)
                else:
                    return ""

            index = self._paired_indices[pair_key]
            paired_values = source.get_paired_values(columns, index)

            # Return the value for the requested field
            for col in columns:
                if field_name.upper() in col.upper():
                    return paired_values.get(col, "")

            # If no direct match, return the first column's value
            return paired_values.get(columns[0], "")

        except Exception as e:
            # Fallback to empty string if file reading fails
            return ""
    
    def _fallback_generate(self, data_type: str, length: Optional[int], 
                          scale: Optional[int]) -> Any:
        """Generate fallback data based on data type."""
        dtype = data_type.upper()
        
        if dtype == "SMALLINT":
            # SMALLINT range: -32,768 to 32,767
            return random.randint(1, 32767)
        
        elif dtype in ("INTEGER", "BIGINT"):
            return random.randint(1, 1000000)
        
        elif dtype in ("DECIMAL", "NUMERIC"):
            # Respect precision and scale constraints
            # length = total digits, scale = decimal places
            if length and scale is not None:
                max_int_digits = length - scale
                max_val = (10 ** max_int_digits) - 1
                min_val = 1
                int_part = random.randint(min_val, max(1, max_val))
                dec_part = random.randint(0, (10 ** scale) - 1)
                return round(int_part + (dec_part / (10 ** scale)), scale)
            else:
                return round(random.uniform(1, 100000), scale or 2)
        
        elif dtype == "DATE":
            return datetime.now() - timedelta(days=random.randint(0, 365))
        
        elif dtype == "TIME":
            return datetime.now().time()
        
        elif dtype == "TIMESTAMP":
            return datetime.now() - timedelta(days=random.randint(0, 365))
        
        elif dtype in ("CHAR", "VARCHAR"):
            # Respect length constraint strictly
            max_len = length or 20
            if max_len > 0:
                min_len = min(1, max_len)  # Ensure min_len <= max_len
                return ''.join(random.choices(string.ascii_letters, k=random.randint(min_len, max_len)))
            else:
                return ""  # Zero-length string if length is 0
        
        elif dtype in ("BINARY", "VARBINARY", "BLOB"):
            # Return hex string representation
            return ''.join(random.choices(string.hexdigits, k=min(length or 20, 64)))
        
        else:
            return ""
