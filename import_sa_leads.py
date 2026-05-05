import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crmtracker.settings')
django.setup()

from crm.models import Contact, Note

sa_leads_data = [
    ("BlackRose Hair Salon", "193 Main Rd, Green Point, Cape Town 8051", "+27 73 248 6130", "4.7", "20", "Hair Braiding", "I have no idea how people make a booking here. Many failed phone calls... messaging them on Instagram, I still don't have a response or call back days later."),
    ("Afro Corner", "33 Strand St, Cape Town City Centre 8001", "+27 21 422 0858", "4.5", "249", "Hair Salon", "Customers warn others about inconsistent pricing with no price list or booking system online."),
    ("Bella's Touch Natural Hair Salon", "44 Lower Main Rd, Observatory 8000", "+27 21 447 1368", "4.6", "122", "Natural Hair", "No online booking — customers rely entirely on walk-ins with no availability info."),
    ("Ground Culture Cafe", "170 Lower Main Rd, Observatory 7925", "+27 78 448 0839", "4.8", "365", "Café/Bar", "No website — customers can't check event schedules or book for comedy nights online."),
    ("Obz Cafe", "115 Lower Main Rd, Observatory 7925", "+27 69 581 3875", "4.0", "1,951", "Restaurant/Bar", "Outdated/no online presence — customers mention unupdated wine menu with no way to check online."),
    ("Cocoa Cha Chi", "Lower Main Rd, Observatory 7935", "+27 64 972 1074", "4.4", "1,387", "Café/Restaurant", "No website — customers can't check hours, menu or events ahead of visiting."),
    ("CAFE 51", "51 Roodebloem Rd, Woodstock 7915", "+27 68 000 7909", "4.4", "332", "Restaurant/Events", "The 10% surcharge was a surprise — no menu or pricing published online, causing confusion."),
    ("Riaan's Auto Repairs", "12 Huguenot St, Parow East 7501", "+27 21 930 6724", "4.6", "197", "Auto Repair", "Excellent service but zero web presence — customers find them only through word of mouth."),
    ("Motor Masters", "Boulevard Park, Bellville 7530", "+27 21 939 0130", "4.4", "164", "Auto Repair", "No website — customers can't book, check pricing or get quotes online."),
    ("Garage 808", "16 Boulevard Park, Bellville 7530", "+27 21 820 3319", "4.6", "80", "BMW Auto Repair", "No website — high-end clientele forced to rely on Google Maps with no online quoting or booking."),
    ("Affordable Tyres & Windscreens Bellville", "402 Voortrekker Rd, Parow East 7501", "+27 21 911 2104", "4.5", "144", "Tyre Shop", "Verbal quotes are unprofessional — no pricing or quote system online."),
    ("Texas Auto Fitment Center", "43 Jan Smuts Rd, Parow 7500", "+27 21 023 1032", "4.3", "68", "Tyre/Auto", "Verbal quotes are unprofessional and result in problems — customer felt scammed due to no written online pricing."),
    ("Central Garage", "40 Joubert St, Parow Valley 7500", "+27 21 931 9913", "4.3", "64", "Auto Repair", "Customer left car for months with no updates — no online job tracking or communication portal."),
    ("Ching's Panel and Spray", "12 Cotte Rd, Lansdowne 7780", "+27 72 359 9161", "4.9", "68", "Panel Beater", "No website — exceptional work but customers can only find them via word of mouth."),
    ("RAZOR AUTOBODY", "25 Section St, Paarden Eiland 7420", "+27 21 510 2056", "4.8", "221", "Panel Beater", "No bookings page — clients describe a spa-like shop but there's no way to book or quote online."),
    ("Goodwood Body & Spray Work", "Townsend Estate, Cape Town 7500", "+27 21 591 4271", "4.8", "45", "Panel Beater", "No website — completely reliant on Google Maps, no quotes or booking online."),
    ("Sprayworx Panelshop", "441 Koeberg Rd, Rugby 7441", "+27 82 255 9495", "4.8", "103", "Panel Beater", "No website — customers can't check availability, get quotes or track repairs online."),
    ("Goodall & Bourne Funeral Undertakers", "10 Church St, Athlone 8000", "+27 21 697 1116", "4.9", "136", "Funeral Home", "No website — grieving families have no way to find service packages, pricing or contact info in advance."),
    ("Tony Wyllie & Co Funeral Home", "469 Voortrekker Rd, Maitland 7405", "+27 21 593 8820", "4.8", "36", "Funeral Home", "No website — families can't access pricing, packages or pre-planning info online."),
    ("Peninsula Funerals", "Tienie Meyer Bypass, Bellville 7530", "+27 21 948 9490", "4.9", "65", "Funeral Home", "No website — no online presence for a business families desperately need to find quickly."),
    ("Doves Funeral Services Observatory", "32 Durham Ave, Salt River 7925", "+27 21 447 1150", "3.8", "41", "Funeral Home", "Doves NEVER contacted us — no client portal, no online death certificate tracking."),
    ("Teach Me 2", "9 Grove Ave, Claremont 7708", "+27 21 300 0971", "4.8", "820", "Tutoring", "No way to browse tutors, subjects or pricing online before contacting them."),
    ("Cape Town Tutors", "20 Brickfield Rd, Salt River 7925", "+27 73 895 9293", "4.8", "58", "Tutoring", "No tutor profiles or subject listings online — clients have to call to find out what's available."),
    ("Elite Tutors", "12 Glenhof Rd, Newlands 7700", "+27 82 696 5717", "5.0", "43", "Tutoring", "No website — parents and students have no way to check availability or book sessions online."),
    ("PRO Cleaning Group", "21 Jan Smuts Rd, Beaconvale 7500", "+27 21 595 0113", "4.9", "140", "Cleaning Services", "No online booking or quote form — clients must call to get pricing."),
    ("Pristine Clean Deep Cleaning", "47 Buitenkant St, Cape Town 8001", "+27 82 769 9232", "4.8", "214", "Cleaning Services", "No website — bookings made via WhatsApp only, no online availability or service menu."),
    ("Shalean Cleaning Services", "39 Harvey Rd, Claremont 7708", "+27 87 153 5250", "4.8", "129", "Cleaning Services", "No online presence — entirely WhatsApp based with no service packages listed anywhere online."),
    ("Grime Away Deep Cleaning", "Albert Rd, Woodstock 7925", "+27 76 268 5913", "4.9", "130", "Deep Cleaning", "No website — all communication via phone/WhatsApp, no pricing or booking page."),
    ("Kitchen Republik Catering", "Salt River, Cape Town 7925", "+27 71 677 1209", "5.0", "73", "Catering", "Replies to queries sometimes slow — no website with menus, packages or online enquiry form."),
    ("Bruce Catering", "50 Marine Dr, Paarden Eiland 7420", "+27 21 510 7753", "4.5", "71", "Catering", "No website — a large, popular caterer relying entirely on referrals with no online presence."),
]

for name, address, phone, rating, reviews, category, pain_point in sa_leads_data:
    contact, created = Contact.objects.get_or_create(
        name=name,
        defaults={
            'company': category,
            'phone': phone,
            'status': 'lead',
            'region': 'sa',
        }
    )
    if created:
        Note.objects.create(
            contact=contact,
            body=f"Address: {address}\nRating: {rating}\nReviews: {reviews}\nCategory: {category}\nPain point: {pain_point}"
        )

print(f"Successfully processed {len(sa_leads_data)} SA leads.")
