import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crmtracker.settings')
django.setup()

from crm.models import Contact, Note

jhb_leads_data = [
    ("T Looks Hair Salon", "731 Bolanibolani Rd, Moletsane, Soweto, 1868", "+27783035205", "N/A", "17", "Hair Salon", "Facebook/TikTok only, no website – relies on social media for all bookings"),
    ("Fair Heads Hair and Beauty Salon", "754 Ralufutso St, Moletsane, Soweto, 1868", "+27631012172", "N/A", "N/A", "Hair Salon", "Fresha listing only, no standalone website or online booking system"),
    ("Fabuleux Hair Studio & Beauty", "2587 Skota St, Orlando East, Soweto, 1804", "+27837933782", "N/A", "16", "Hair Salon", "Instagram and Facebook only, no website – relies entirely on social media DMs"),
    ("Browlink Studio", "Soweto Business Hub, Maponya Mall, 2127 Chris Hani Rd, Klipspruit, Soweto, 1809", "+27687710823", "4.8", "306", "Beauty Salon", "WhatsApp-only bookings, no website – customers must DM to schedule"),
    ("Pink Apple Beauty Lounge Braam", "42 Biccard St, Braamfontein, Johannesburg, 2001", "+27645583861", "N/A", "N/A", "Beauty Salon", "Instagram and WhatsApp only, no website – no way to view services or book online"),
    ("TBS Makeover and Beauty Salon", "Shop 7, 93 Juta St, Braamfontein, Johannesburg, 2001", "+27845696306", "N/A", "N/A", "Beauty Salon", "No website – Google Maps listing only, no online booking"),
    ("Queens Hair Paradise Salon", "42 Biccard St, Braamfontein, Johannesburg, 2017", "+27100650138", "N/A", "N/A", "Hair Salon", "Facebook-only presence, no website or booking system"),
    ("Kris Hair Cut", "4 Ameshoff St, Braamfontein, Johannesburg, 2001", "+27786034299", "N/A", "N/A", "Barbershop", "No website, unverified Fresha listing – relies on foot traffic only"),
    ("The Soweto Barbershop", "Chris Hani Rd, Diepkloof Diepmeadow, Soweto, 2001", "+27734277147", "N/A", "N/A", "Barbershop", "No website – Facebook and Fresha listing only, no online booking"),
    ("Blvck Valvet Barbershop", "3933 Molakoane St, Orlando East, Soweto, 1804", "+27818693523", "N/A", "N/A", "Barbershop", "Facebook page only, no website – all bookings via WhatsApp"),
    ("Suka Emabozeni Barbershop", "916 Indwa St, Naledi, Soweto, 1868", "+27659364584", "N/A", "N/A", "Barbershop", "Instagram and Fresha listing only, no dedicated website"),
    ("Livzo The Barber", "1305 Legwale St, Mapetla, Soweto, 1818", "+27740671006", "N/A", "N/A", "Barbershop", "Facebook-only presence, no website – customers book via phone call"),
    ("The Groomsroom", "2229 Maredi St, Moletsane, Soweto, 1868", "", "N/A", "N/A", "Barbershop", "Fresha listing only, no phone number published, no website"),
    ("The Gspot Barber Studio", "23 John Pop Rd, Eldorado Park, Soweto, 1811", "", "N/A", "N/A", "Barbershop", "No website, no reviews yet – Fresha listing is only online presence"),
    ("Kei's Barbershop Rosebank", "Shop G24B Phase 2, The Zone, 31 Tyrwhitt Ave, Rosebank, Johannesburg, 2196", "", "N/A", "N/A", "Barbershop", "Google Maps listing only – no website, no online booking"),
    ("Mediterranean Barber Randburg", "G20 Victory Park Shopping Centre, Cnr 2nd Ave & Rustenburg Rd, Randburg, 2125", "+27795008160", "N/A", "N/A", "Barbershop", "No website – relies on phone calls and walk-ins only"),
    ("Scara Panelbeaters", "129 Midway St, Eldorado Park, Soweto, 1811", "+27119804765", "N/A", "N/A", "Panel Beater", "No online quote system or gallery – customers cannot request quotes online"),
    ("TCTS Autobody", "Unit 10 Motor City, Cnr Malibongwe Dr & Hammer Ave, Strydom Park, Randburg, 1700", "+27106150964", "N/A", "N/A", "Panel Beater", "No online booking – relies on WhatsApp and phone for all queries"),
    ("Bodytechnique Panelbeaters & Spraypainters", "538 Dane Rd, Glen Austin, Midrand, 1685", "+27105900690", "N/A", "N/A", "Panel Beater", "No quote form, no portfolio, no reviews integration online"),
    ("Tiger Auto Services", "Unit 12, 23 Staal St, Kya Sand, Randburg", "+27115687737", "N/A", "N/A", "Auto Repair", "Facebook presence only, no website – customers contact via Facebook Messenger"),
    ("Pera Auto Panelbeaters", "5 Tungsten Rd, Strydom Park, Randburg, 2169", "", "N/A", "N/A", "Panel Beater", "Directory listing only – no website, no online quotes, no reviews page"),
    ("MotorPro Midrand", "Unit B22, Midrand China Town Mall, Midrand, 1685", "", "N/A", "N/A", "Auto Repair", "Google Maps listing only – no website or online booking system"),
    ("Wandies Place", "618 Makhalemele St, Dube, Soweto, 1801", "+27119822796", "4.0", "77", "Restaurant", "Has basic website but no online reservation or menu ordering system"),
    ("Robby's Place", "Cnr Chris Hani & Nicholas St, Pimville, Soweto", "+27119337965", "4.3", "74", "Restaurant", "No website – Facebook-only presence, no online reservations"),
    ("Chaf Pozi Traditional Restaurant", "Cnr Kingsley Sithole & Nicholas St, Orlando East, Soweto", "+27817975756", "3.7", "90", "Restaurant", "Has basic website but no online booking, no delivery integration"),
    ("Vuyos Restaurant", "6974 Vilakazi St, Orlando West, Soweto, 1804", "", "3.7", "39", "Restaurant", "Has website but no online reservations, no WhatsApp booking link"),
    ("Chez Alina Restaurant", "3373 Masemola St, Dobsonville, Soweto, 1863", "+27818955181", "4.3", "133", "Restaurant", "Has basic website – no online table booking or e-menu with photos"),
    ("Only1Cuisine Catering", "90 Van Onselen Rd, Meadowlands West, Soweto", "+27786698069", "N/A", "N/A", "Catering", "Website is basic – no online quote form or event planning portal"),
    ("Bright Stars Tutoring Services", "781 Khanyile St, Zola North, Soweto", "+27814418415", "N/A", "N/A", "Tutoring Centre", "Facebook page only – parents cannot view syllabus or book sessions online"),
    ("Bright Young Minds Tuition Centre", "Shop 2, William Hill Ave, The Lake Shopping Centre, Denlee, Germiston, 1401", "+27848544418", "4.9", "9", "Tutoring Centre", "Has website but no online enrolment form or timetable display"),
    ("LaundryPond Soweto", "1 Chaka St, Dlamini 2, Soweto", "+27119861001", "N/A", "N/A", "Laundromat", "Has website but no online pickup scheduling or pricing page"),
    ("Aqua Room Laundry", "1406 Mavi St, Central Western Jabavu, Soweto, 1809", "+27817873984", "N/A", "N/A", "Laundromat", "Basic WordPress site only – no online booking, no service pricing listed"),
    ("R Louw Laundromat", "Roodepoort, Gauteng", "", "N/A", "N/A", "Laundromat", "Facebook and Instagram only, no website – phone/DM for all queries"),
    ("Valley View Cleaners Laundromat", "Unit 12 Valley View Centre, Fourways, Johannesburg", "", "N/A", "N/A", "Laundromat", "No website – relies on walk-in traffic and word of mouth only"),
    ("LMS Electrical Contractors", "53 Republic Rd, Blairgowrie, Randburg", "+27827799834", "N/A", "N/A", "Electrician", "Has basic website but no service request form or customer portal"),
    ("Thomas Knowles Plumbing", "138 President St, Germiston, 1401", "+27118255500", "N/A", "N/A", "Plumber", "Has website but outdated design with no online bookings"),
    ("Burgess Plumbing Edenvale", "Edenvale, Gauteng", "+27860404142", "N/A", "N/A", "Plumber", "Facebook page only – no website, no online request form"),
    ("Thomas Tyres Boksburg", "Cnr North Rand & Rietfontein Rd, Shop 8-10, Venter Centre, Boksburg North, 1459", "+27118262233", "N/A", "N/A", "Tyre Shop", "Has basic website but no online fitment booking or stock checker"),
    ("KOENIC Wheel Warehouse Edenvale", "143 Van Riebeeck Ave, Edenvale, 1609", "+27116097913", "4.5", "76", "Tyre Shop", "Has website but no online appointment booking or tyre-finder tool"),
    ("Pick-A-Tyre Elandsfontein", "168 Barbara Rd, Germiston, Gauteng", "+27118280406", "N/A", "N/A", "Tyre Shop", "Has website but zero online reviews and no appointment booking system"),
    ("Ginger Hair Salon", "74 11th St, Parkmore, Sandton, 2196", "+27113267456", "N/A", "N/A", "Hair Salon", "Has website but no online booking or WhatsApp button integration"),
    ("Cliche Unisex Salon", "Shop 15, Kilburn Shopping Centre, 117 Kilburn Rd, Discovery, Roodepoort, 1709", "+27792642635", "N/A", "N/A", "Beauty Salon", "Has website but no online booking – clients must call or walk in"),
    ("Saks Hairdressing Germiston", "Shop 12, The Reef Shopping Centre, Norton Small Farms, Germiston, 1401", "+27649834463", "4.9", "629", "Hair Salon", "Fresha only – no standalone website, no brand-owned booking page"),
    ("Catwalk Hair Beauty & Nails Edenvale", "Shop 24, Van Riebeeck Mall, 39 Van Riebeeck Ave, Edenvale, 1609", "+27114534907", "N/A", "8", "Beauty Salon", "Has basic website but no online booking or gallery of work"),
    ("Home Barber SA Soweto", "266 Legwale St, Naledi, Soweto, 1868", "+27846444142", "5.0", "8", "Barbershop", "Has website but no online appointment booking system"),
    ("Randpark Hair & Beauty", "Randpark Ridge, Randburg, Johannesburg", "+27117913929", "N/A", "N/A", "Hair Salon", "Phone-book and Yellow Pages listing only – no website, no social media"),
    ("Share Hair Salon Randburg", "Randburg, Johannesburg", "+27118861105", "N/A", "N/A", "Hair Salon", "Yellow Pages listing only – no website, relies entirely on phone enquiries"),
    ("Eat A Bit Catering & Decor", "Randburg, Johannesburg", "", "N/A", "N/A", "Catering", "Facebook-only presence – no website, no menu page, no quote request form"),
    ("Mulberry Catering Randburg", "Unit 42 Barbeque Corner, 27 Dytchley Rd, Barbeque Downs, Randburg", "", "N/A", "N/A", "Catering", "Facebook page only – email and Messenger are the only contact options"),
    ("Exclusive Style Hair & Beauty Studio", "Germiston, Gauteng", "", "N/A", "N/A", "Hair Salon", "Facebook page with nearly 10,000 followers but no website – losing bookings daily"),
]

added = 0
skipped = 0

for name, address, phone, rating, reviews, category, pain_point in jhb_leads_data:
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
        added += 1
    else:
        skipped += 1

print(f"Done — {added} leads added, {skipped} already existed.")
