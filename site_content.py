"""
Copy and structure for the v3 (templated) pages.

Everything here is lifted from the existing site (service lists, FAQ answers,
ceramic process, reviews) or from Tony's direct answers. Prices are NOT typed
here — templates read them from app.BASE_PRICES / ADDON_PRICES so the cards,
the pricing tables and the email estimate can never disagree.

To change a service description, edit it here and push.
"""

PHONE_DISPLAY = "(216) 903-4783"
PHONE_TEL = "+12169034783"
EMAIL = "tonysdetailing.net@gmail.com"
GOOGLE_REVIEWS_URL = "https://www.google.com/search?q=Tony%27s+Detailing+Chardon+OH"

# Social profiles. Leave a value empty to hide its icon — never link a
# placeholder. Send Claude the real URLs to fill these in.
SOCIAL = {
    "facebook": "",
    "instagram": "",
    "nextdoor": "",
    "yelp": "",
}

# ── Shared FAQ answers (from /faq) ──────────────────────────────────────────
FAQ = {
    "duration": (
        "How long does a detail take?",
        "Most cars and SUVs take about 2–5 hours depending on the service and "
        "condition. An exterior or interior detail is on the shorter end; a Full "
        "Detail takes longer. We give you a time estimate when we confirm your booking.",
    ),
    "utilities": (
        "Do you need access to water and power?",
        "Yes. We need access to a standard electrical outlet, and depending on the "
        "job we may also need an outdoor water spigot. If you're unsure what you "
        "have available, let us know in your quote request and we can plan around it.",
    ),
    "payment": (
        "What payment methods do you accept?",
        "We currently accept cash only. Payment is due after the detail is finished "
        "and you're happy with the result.",
    ),
    "weather": (
        "What's your weather policy?",
        "Because we're mobile, weather matters. Light conditions are usually fine, "
        "but heavy rain, storms, or extreme cold can affect quality, so we may "
        "reschedule to protect the result. If we need to move your appointment "
        "we'll reach out as early as possible to find a new time.",
    ),
    "upcharge": (
        "Why might there be an upcharge?",
        "Base prices assume normal wear. Heavy pet hair, deep staining, smoke or "
        "odor, and excessive debris take extra time and materials, so they can add "
        "to the price. Any upcharge is estimated and confirmed with you on arrival, "
        "before any work begins — no surprises at the end.",
    ),
    "home": (
        "Do I need to be home?",
        "You don't have to be home the whole time, but we do need access to the "
        "vehicle and a spot to work — a driveway, parking area, or garage. We come "
        "to your home or office and set up on site.",
    ),
    "advance": (
        "How far in advance should I book?",
        "A few days ahead is ideal, especially on weekends, but we'll always try to "
        "fit you in sooner when the schedule allows. We confirm within 24 hours. "
        "Please give at least 24 hours' notice to cancel or reschedule.",
    ),
    "stains": (
        "Will every stain come out?",
        "Some carpet, headliner, and upholstery stains have set into the fibers and "
        "won't fully release with standard interior treatment. We tell you up front, "
        "on arrival, what's realistic.",
    ),
    "ceramic_care": (
        "How do I care for a ceramic coating?",
        "Hand wash or touchless wash only. Automatic and tunnel washes can scratch "
        "through the coating, clay barring a coated surface strips it, and strong "
        "acidic cleaners break it down early.",
    ),
    "ceramic_correction": (
        "Is paint correction included with a ceramic coating?",
        "Both ceramic packages include a single-stage enhancement polish, which "
        "lifts light swirls and improves gloss. Multi-stage paint correction is "
        "quoted separately. Coatings lock in whatever condition the paint is in, so "
        "if yours needs correction first, tell us and we'll take a look.",
    ),
    "correction_limits": (
        "Can every scratch be polished out?",
        "No. Rust, deep paint oxidation, and salt damage are structural — they "
        "require body work, not detailing. We'll tell you what's realistic after "
        "we inspect the paint.",
    ),
    "correction_quote": (
        "Why isn't there a set price?",
        "How much correction a vehicle needs depends entirely on the condition of "
        "its paint, so every correction job is quoted after we inspect it. You "
        "approve the price before any work begins.",
    ),
}

# ── The six services, in the order Tony listed them ────────────────────────
# price_key: row in app.BASE_PRICES (priced by vehicle size)
# flat_price: key in app.ADDON_PRICES (one price, any size)
# neither: quoted after inspection
SERVICES = [
    {
        "slug": "interior-detailing",
        "name": "Full Interior Detail",
        "price_key": "Interior Detail",
        "image": "svc-interior",
        "image_alt": "Detailed leather rear seats",
        "short": "Every interior surface cleaned, conditioned, and deodorized.",
        "title": "Interior Detailing in Chardon & Northeast Ohio",
        "meta": "Mobile interior detailing — full vacuum, surfaces, glass, vents and "
                "deodorizing, done in your driveway. Get a free quote.",
        "intro": "A complete interior clean done right in your driveway — seats, "
                 "floors, trunk, surfaces, glass and vents. We walk the vehicle "
                 "with you first and confirm any condition upcharges before we start.",
        "included": [
            "Full vacuum — seats, floors, trunk",
            "Surface & console wipe-down",
            "Interior glass clean",
            "Vent brush cleaning",
            "Interior spray & deodorize",
        ],
        "addons": ["Leather Conditioning", "Odor Eliminator"],
        "faqs": ["duration", "upcharge", "stains", "utilities"],
    },
    {
        "slug": "wash-n-wax",
        "name": "Wash n' Wax",
        "price_key": "Wash n' Wax",
        "image": "svc-wash",
        "image_alt": "SUV covered in foam during a hand wash",
        "short": "Our exterior tier: foam wash, clay bar decontamination, and a "
                 "protective wax finish.",
        "title": "Wash n' Wax — Mobile Exterior Detailing",
        "meta": "Foam wash, clay bar decontamination and a protective wax finish, "
                "brought to your home or office in Northeast Ohio.",
        "intro": "Our exterior-only service. A foam pre-soak and hand wash, clay "
                 "bar decontamination to pull embedded grime off the paint, and a "
                 "protective wax finish — wheels, tires and glass included.",
        "included": [
            "Foam wash, rinse & hand dry",
            "Clay bar decontamination",
            "Protective wax finish",
            "Tire shine & wheel clean",
            "Exterior window & trim wipe",
        ],
        "addons": ["Headlight Restoration"],
        "faqs": ["duration", "utilities", "weather", "advance"],
    },
    {
        "slug": "paint-correction",
        "name": "Paint Correction",
        "price_key": None,
        "image": "svc-correction",
        "image_alt": "Glossy white paint after detailing",
        "short": "Machine polishing to restore gloss and reduce swirl marks — "
                 "quoted after we inspect your paint.",
        "title": "Paint Correction — One-Step & Multi-Step",
        "meta": "One-step and multi-step paint correction in Northeast Ohio. Every "
                "job is quoted after a paint inspection. Request a free quote.",
        "intro": "Paint correction is machine polishing of your clear coat to bring "
                 "back gloss and reduce swirl marks. We offer a one-step correction "
                 "and more extensive multi-step correction. Because every vehicle's "
                 "paint is different, correction is always quoted separately, after "
                 "we've inspected it.",
        "included": [
            "Paint inspection before any quote",
            "One-step correction",
            "More extensive multi-step correction",
            "Quote approved by you before work begins",
        ],
        "addons": [],
        "faqs": ["correction_quote", "ceramic_correction", "correction_limits"],
    },
    {
        "slug": "ceramic-coating",
        "name": "Ceramic Coating",
        "price_key": "Ceramic Coating (3-Year)",
        "image": "svc-ceramic",
        "image_alt": "Blue Volvo with glossy paint in a driveway",
        "short": "Long-term paint protection with full decontamination and polish "
                 "prep. 3-Year and Elite 5-Year packages.",
        "featured": True,
    },
    {
        "slug": "full-detail",
        "name": "Full Detail",
        "price_key": "Full Detail",
        "image": "svc-full-detail",
        "image_alt": "White Audi with doors open during a full detail",
        "short": "The complete package — interior and exterior plus a wax "
                 "protection coat. Our most popular service.",
        "badge": "Most Popular",
        "title": "Full Detail — Interior + Exterior, We Come To You",
        "meta": "Our most popular service: a complete interior and exterior detail "
                "plus a wax protection coat, done at your home or office.",
        "intro": "The complete package and our best value — everything in our "
                 "Interior Detail plus a full exterior wash and a wax protection "
                 "coat, finished with a walk-around so you can see the result.",
        "included": [
            "Full exterior wash, wheels & glass",
            "Everything in the Interior Detail",
            "Wax protection coat",
            "Post-service walk-around",
        ],
        "note": "Full Detail is the minimum service for trips outside our standard "
                "15-mile area.",
        "addons": ["Clay & Iron Decontamination", "Leather Conditioning", "Headlight Restoration"],
        "faqs": ["duration", "upcharge", "payment", "home"],
    },
    {
        "slug": "headlight-restoration",
        "name": "Headlight Restoration",
        "price_key": None,
        "flat_price": "Headlight Restoration",
        "image": "svc-headlight",
        "image_alt": "Clear headlight after restoration",
        "short": "Foggy, yellowed headlights restored to clear — standalone or as "
                 "an add-on.",
        "title": "Headlight Restoration — Clear Lenses, Flat Rate",
        "meta": "Foggy, yellowed headlights restored to clear. Flat rate per set, "
                "standalone or added to any detail. Mobile service in NE Ohio.",
        "intro": "Foggy, yellowed headlights restored to clear — improving "
                 "nighttime visibility and giving your vehicle a sharper, more "
                 "finished look.",
        "included": [
            "Removes yellowing & haze from foggy lenses",
            "Flat rate per set, any vehicle",
            "Standalone or added to any detail",
        ],
        "before_after": True,
        "addons": [],
        "faqs": ["duration", "utilities"],
    },
]

SERVICE_BY_SLUG = {s["slug"]: s for s in SERVICES}

# Display order on the homepage / services grid: flagship first.
GRID_ORDER = [
    "ceramic-coating", "full-detail", "interior-detailing",
    "wash-n-wax", "paint-correction", "headlight-restoration",
]

ADDON_COPY = {
    "Leather Conditioning": "Cleans, softens & protects leather seats and trim",
    "Clay & Iron Decontamination": "Iron & fallout removal",
    "Odor Eliminator": "Targeted treatment for smoke, pet & musty odors",
    "Headlight Restoration": "Removes yellowing & haze from foggy lenses",
}

WHY_US = [
    ("map-pin", "We Come To You",
     "Home or office — your driveway becomes the detail bay. We just need an "
     "outlet and, for some jobs, a water spigot."),
    ("search", "Attention To Detail",
     "Vents, seams, door jambs, and the spots most crews skip. Before-and-after "
     "photos on every job."),
    ("timer", "Quality Over Speed",
     "We do fewer cars, but do them right. Your vehicle gets the time it needs, "
     "not a rushed slot."),
    ("spray-can", "A Proper Process",
     "Foam pre-wash, clay bar decontamination, and full coating prep — the steps "
     "that make results last."),
    ("hand-heart", "Straight Answers",
     "Your quote is confirmed on arrival, before any work begins. We tell you up "
     "front what a detail can and can't fix."),
]

# Verbatim from Tony's Google reviews (see /reviews).
REVIEWS = [
    ("Megan", "SUV",
     "Tony did a great job detailing my SUV. Everything looks and smells great. I "
     "reached out to see if he could help find a ring I dropped between the seats. "
     "Not only did he go above and beyond cleaning the car, he took out the seat "
     "and dug through the carpet and found my ring. I am forever grateful and "
     "highly recommend having Tony take care of your needs."),
    ("James Babcock", "Truck",
     "Tony took care of my Frontier King Cab carpet that I accidentally fed some "
     "Irish Stew from Cincinnati. Excellent results and he was very professional, "
     "courteous, and efficient at getting it done. Also detailed the dash and vents "
     "that I had neglected for a while. Hard to find conscientious young "
     "entrepreneurs that get the job done, show up when they say, and go above and "
     "beyond. Highly recommend giving him a chance to literally shine!"),
    ("Stephanie Slogar", "",
     "Tony did a great job! Super happy with the whole process. Tony is super nice "
     "and thorough. Easy and accomodating scheduling. Definitely would highly "
     "recommend him to others!"),
    ("Christa Boske", "",
     "Tony and his associate did a PHENOMENAL job on the interior and exterior. "
     "They were very polite and professional."),
    ("Ilene McMullen", "",
     "Tony did an awesome job on my son's car- very prompt, professional and "
     "thorough. Great communication- would not hesitate to call him again!"),
    ("Hector Diaz-Stringel", "",
     "Excellent job. Very meticulous. Will hire Tony to do my wife's car soon!"),
]

WORK_PHOTOS = [
    (20, "White Audi, doors open mid-detail"),
    (35, "Blue Volvo XC60 after an exterior detail"),
    (21, "Audi interior with brown leather"),
    (45, "Volvo in a foam pre-wash"),
    (38, "Detailed black leather front seats"),
    (14, "Rear leather seats after an interior detail"),
    (26, "Third-row SUV interior after cleaning"),
    (22, "White Audi A5 Sportback after a detail"),
]

TOWNS = [
    "Chardon", "Chesterland", "Chagrin Falls", "Gates Mills", "Kirtland",
    "Hunting Valley", "Waite Hill", "Willoughby", "Mentor", "Concord",
    "Painesville", "Munson", "Novelty", "Russell",
]

AREA_PAGES_LABELS = {
    "gates-mills": "Gates Mills",
    "hunting-valley": "Hunting Valley",
    "pepper-pike": "Pepper Pike",
    "moreland-hills": "Moreland Hills",
    "chagrin-falls": "Chagrin Falls",
    "bentleyville": "Bentleyville",
}

# Ad landing pages (Meta). Not in the sitemap; noindex.
LANDING_PAGES = {
    "full-detail": {
        "service": "full-detail",
        "eyebrow": "Full Detail · Winter Prep",
        "h1": "Get Your Car Ready For Winter",
        "lede": "A complete interior and exterior detail plus a wax protection coat "
                "— done in your driveway before the salt and slush season.",
        # Leave empty unless Tony has a real, current promotion to run.
        "promo": "",
        "title": "Full Detail — Mobile Detailing in Northeast Ohio",
        "cta": "GET A FREE QUOTE",
    },
    "ceramic-coating": {
        "service": "ceramic-coating",
        "eyebrow": "Ceramic Coating",
        "h1": "Protect Your Paint For Years",
        "lede": "Full decontamination, a single-stage enhancement polish, and a "
                "hand-applied ceramic coating — about six hours, right at your home.",
        "promo": "",
        "title": "Ceramic Coating — Mobile Paint Protection in NE Ohio",
        "cta": "REQUEST CERAMIC COATING INFORMATION",
    },
}
