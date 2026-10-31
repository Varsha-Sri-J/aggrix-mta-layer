"""Curated datasets and providers for realistic e-commerce synthetic data generation."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import List, Tuple

# Pre-curated list of realistic Shopify-style store brand names
STORE_NAMES: List[str] = [
    "Nordic Living Goods",
    "Velvet & Vine Apparel",
    "Aura Athletics",
    "Apex Tech Lab",
    "Urban Botanica",
    "Solstice Home & Hearth",
    "Loom & Craft Goods",
    "Terra Essentials",
    "Prism Studio Audio",
    "Haven Kitchenware",
    "Kinfolk Leather Co",
    "Summit Outdoor Gear",
    "Lumina Skincare",
    "Atlas Coffee Roasters",
    "Beacon Maritime Supply",
]

FIRST_NAMES: List[str] = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Shirley", "Eric", "Angela", "Jonathan", "Helen", "Stephen", "Anna",
    "Larry", "Brenda", "Justin", "Pamela", "Scott", "Nicole", "Brandon", "Emma",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Gregory", "Christine", "Frank", "Debra",
    "Alexander", "Rachel", "Raymond", "Catherine", "Patrick", "Carolyn", "Jack", "Janet",
    "Dennis", "Ruth", "Jerry", "Maria", "Tyler", "Heather", "Aaron", "Diane",
]

LAST_NAMES: List[str] = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
    "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales",
    "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson",
    "Bailey", "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward",
    "Richardson", "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray",
]

EMAIL_DOMAINS: List[str] = [
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "icloud.com",
    "proton.me",
    "fastmail.com",
    "hey.com",
]

# Product catalog templates organized by category: (category_code, item_name, base_price)
PRODUCT_TEMPLATES: List[Tuple[str, str, Decimal]] = [
    # Apparel (APP)
    ("APP", "Organic Heavyweight Cotton T-Shirt", Decimal("34.00")),
    ("APP", "Relaxed Fit Selvedge Denim Jeans", Decimal("88.50")),
    ("APP", "Merino Wool Crewneck Sweater", Decimal("128.00")),
    ("APP", "Waterproof Breathable Rain Shell", Decimal("165.00")),
    ("APP", "Vintage Pigment-Dyed Pullover Hoodie", Decimal("72.00")),
    ("APP", "Garment-Washed Linen Camp Shirt", Decimal("64.00")),
    ("APP", "Stretch Cotton Chino Trousers", Decimal("78.00")),
    ("APP", "Thermal Waffle Knit Long Sleeve", Decimal("46.00")),
    ("APP", "Technical Packable Windbreaker", Decimal("110.00")),
    ("APP", "Tailored Unstructured Linen Blazer", Decimal("195.00")),
    ("APP", "Performance Stretch Athletic Shorts", Decimal("48.00")),
    ("APP", "Pima Cotton Pocket Undershirt 2-Pack", Decimal("42.00")),
    ("APP", "Heavyweight Brushed Flannel Overshirt", Decimal("85.00")),
    ("APP", "French Terry Zip-Up Track Jacket", Decimal("92.00")),
    ("APP", "Seamless Moisture-Wicking Baselayer", Decimal("54.00")),
    # Footwear (FTW)
    ("FTW", "Classic White Leather Court Sneakers", Decimal("118.00")),
    ("FTW", "All-Weather Vibram Trail Running Shoes", Decimal("145.00")),
    ("FTW", "Waterproof Nubuck Chelsea Boots", Decimal("195.00")),
    ("FTW", "Ergonomic Memory Foam Lounging Slides", Decimal("38.00")),
    ("FTW", "Low-Profile Canvas Skate Shoes", Decimal("58.00")),
    ("FTW", "Gore-Tex Mid Mountain Hiking Boots", Decimal("225.00")),
    ("FTW", "Suede Handcrafted Penny Loafers", Decimal("168.00")),
    ("FTW", "Minimalist Zero-Drop Road Running Shoes", Decimal("130.00")),
    # Electronics (ELE)
    ("ELE", "Active Noise Cancelling Wireless Headphones", Decimal("279.99")),
    ("ELE", "Compact Bluetooth 5.3 Waterproof Speaker", Decimal("79.95")),
    ("ELE", "Fast Magnetic 15W Wireless Charging Pad", Decimal("39.99")),
    ("ELE", "Customizable Mechanical Keyboard RGB", Decimal("139.00")),
    ("ELE", "Ergonomic Vertical Wireless Mouse", Decimal("64.50")),
    ("ELE", "High-Resolution OLED Smart Fitness Band", Decimal("99.00")),
    ("ELE", "Multi-Port 100W GaN Fast Wall Charger", Decimal("59.00")),
    ("ELE", "Precision Studio Desktop USB-C DAC", Decimal("189.00")),
    ("ELE", "Ultra-Slim 8-in-1 Aluminum USB-C Hub", Decimal("49.99")),
    ("ELE", "Smart Ambient Auto-Dimming Desk Lamp", Decimal("89.95")),
    # Home & Kitchen (HOM)
    ("HOM", "Enameled Cast Iron Dutch Oven 6qt", Decimal("120.00")),
    ("HOM", "Artisan Ceramic Pour-Over Dripper Set", Decimal("45.00")),
    ("HOM", "Stoneware Dinner Plate Set of 4", Decimal("68.00")),
    ("HOM", "French Terry Woven Cotton Throw Blanket", Decimal("75.00")),
    ("HOM", "Hand-Poured Soy Botanical Candle 12oz", Decimal("28.00")),
    ("HOM", "End-Grain Acacia Hardwood Cutting Board", Decimal("52.00")),
    ("HOM", "Double-Walled Stainless Steel French Press", Decimal("48.00")),
    ("HOM", "Damascus Steel 8-inch Chef Knife", Decimal("115.00")),
    ("HOM", "Japanese Organic Cotton Bath Towel Set", Decimal("62.00")),
    ("HOM", "Insulated Vacuum Water Bottle 32oz", Decimal("34.00")),
    # Beauty & Wellness (BEA)
    ("BEA", "Multi-Peptide Hydrating Daily Serum", Decimal("42.00")),
    ("BEA", "Botanical Foaming Gentle Facial Cleanser", Decimal("26.00")),
    ("BEA", "Cold-Pressed Rosehip Facial Treatment Oil", Decimal("36.00")),
    ("BEA", "Invisible Zinc Mineral Sunscreen SPF 50", Decimal("32.00")),
    ("BEA", "Dead Sea Mineral Restorative Bath Salts", Decimal("22.50")),
    ("BEA", "Overnight Nourishing Ceramide Barrier Balm", Decimal("48.00")),
    ("BEA", "Niacinamide Pore Refining Exfoliating Toner", Decimal("28.00")),
    ("BEA", "Shea & Cocoa Butter Ultra-Repair Hand Salve", Decimal("18.00")),
    # Accessories (ACC)
    ("ACC", "Full-Grain Vegetable Tanned Leather Wallet", Decimal("55.00")),
    ("ACC", "Polarized Handcrafted Acetate Sunglasses", Decimal("89.00")),
    ("ACC", "Heavyweight 16oz Waxed Canvas Tote Bag", Decimal("45.00")),
    ("ACC", "Weather-Resistant 24L Commuter Backpack", Decimal("118.00")),
    ("ACC", "Ribbed 100% Cashmere Winter Beanie", Decimal("65.00")),
    ("ACC", "Solid Brass Key Clip & Leather Lanyard", Decimal("24.00")),
    ("ACC", "Italian Saffiano Leather Passport Cover", Decimal("38.00")),
    ("ACC", "Woven Heavy Gauge Cotton Webbed Belt", Decimal("29.00")),
]


def slugify(text: str) -> str:
    """Convert a human-readable title into an URL-friendly alphanumeric slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")
