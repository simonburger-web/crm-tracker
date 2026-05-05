import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crmtracker.settings')
django.setup()

from crm.models import Contact, Note

leads_data = [
    ("The Henry", "2301 N Akard St Suite 250, Dallas TX 75201", "+1 972-677-9560", "4.4", "3,443", "Restaurant"),
    ("Crown Block Dallas", "300 Reunion Blvd E, Dallas TX 75207", "+1 214-321-3149", "4.1", "1,724", "Restaurant"),
    ("Monarch Restaurant", "1401 Elm St 49th Floor, Dallas TX 75201", "+1 214-945-2222", "4.3", "1,819", "Restaurant"),
    ("Dallas Plumbing & Air Conditioning", "11055 Plano Rd, Dallas TX 75238", "+1 469-489-1061", "4.6", "1,192", "Plumbing/HVAC"),
    ("Lovefield Auto Repair", "2444 Inwood Rd Ste A, Dallas TX 75235", "+1 214-638-7660", "4.2", "220", "Auto Repair"),
    ("Tribeca Plumbing Inc", "6211 W Northwest Hwy c251, Dallas TX 75225", "+1 214-402-5454", "4.8", "425", "Plumbing"),
    ("Metro Flow Plumbing", "3730 Dilido Rd #422, Dallas TX 75228", "+1 214-328-7371", "4.9", "1,378", "Plumbing"),
    ("Manuel Diaz Law Firm", "8100 John W. Carpenter Fwy Suite 200, Dallas TX 75247", "+1 855-502-0454", "4.6", "2,374", "Law Firm"),
    ("Udeshi Law Firm", "2201 Main St #600, Dallas TX 75201", "+1 817-770-0694", "4.4", "250", "Law Firm"),
    ("Tangerine Salon", "7949 Walnut Hill Ln #105, Dallas TX 75230", "+1 972-236-4725", "4.9", "1,840", "Hair Salon"),
    ("Lure Salon", "3839 McKinney Ave #100, Dallas TX 75204", "+1 214-919-5873", "4.8", "745", "Hair Salon"),
    ("Voss Salon", "4640 McKinney Ave #190, Dallas TX 75205", "+1 877-424-6722", "4.6", "542", "Hair Salon"),
    ("24 Hour Fitness (N Central)", "11100 N Central Expy, Dallas TX 75243", "+1 214-360-0024", "4.3", "1,351", "Gym"),
    ("24 Hour Fitness (Fort Worth Ave)", "2300 Fort Worth Ave, Dallas TX 75211", "+1 214-377-2559", "3.9", "816", "Gym"),
    ("Life Time Fitness", "5910 N Central Expy, Dallas TX 75206", "+1 214-624-5800", "3.8", "328", "Gym"),
    ("Equinox Highland Park", "4023 Oak Lawn Ave, Dallas TX 75219", "+1 214-443-9009", "3.4", "279", "Gym"),
    ("Recess Fitness Club", "5706 E Mockingbird Ln #310, Dallas TX 75206", "+1 972-914-7765", "4.7", "558", "Gym"),
    ("Dallas Dental Group", "15123 Prestonwood Blvd #140, Dallas TX 75248", "+1 972-581-9311", "4.9", "731", "Dentist"),
    ("MINT Dentistry Uptown", "2520 Fairmount St Suite 100, Dallas TX 75201", "+1 469-440-7149", "4.7", "1,008", "Dentist"),
    ("J Chester & Associates CPA", "8140 Walnut Hill Ln #430, Dallas TX 75231", "+1 214-330-4682", "4.6", "103", "CPA"),
    ("Reeves Family Plumbing", "13346 Bee St, Dallas TX 75234", "+1 972-247-3763", "4.7", "165", "Plumbing"),
    ("Bailey & Galyen Attorneys", "2777 N Stemmons Fwy Suite 1150, Dallas TX 75207", "+1 972-449-1241", "4.7", "919", "Law Firm"),
    ("Reliant Plumbing Dallas", "2702 Manor Way, Dallas TX 75235", "+1 214-550-0028", "4.5", "229", "Plumbing"),
    ("Salon 5014", "5014 Miller Ave, Dallas TX 75206", "+1 469-426-4308", "4.6", "396", "Hair Salon"),
    ("Mother Modern Plumbing", "6060 N Central Expy Suite 770, Dallas TX 75206", "+1 469-206-9515", "4.9", "284", "Plumbing"),
    ("Abram & Associates CPA", "123 W Illinois Ave, Dallas TX 75224", "+1 214-941-3311", "4.9", "143", "CPA"),
    ("Carter & Company Accounting", "325 N St Paul St Suite 3100, Dallas TX 75201", "+1 469-317-2999", "5.0", "112", "CPA"),
    ("House of Dear Salon", "2604 Hibernia St, Dallas TX 75204", "+1 214-397-0700", "4.5", "830", "Hair Salon"),
    ("Highlands Auto Center", "10524 E NW Hwy, Dallas TX 75238", "+1 972-233-8882", "4.5", "215", "Auto Repair"),
    ("Texas Auto Repair and Tire", "4870 Sunnyvale St, Dallas TX 75216", "+1 972-685-0968", "4.9", "616", "Auto Repair"),
]

for name, address, phone, rating, reviews, category in leads_data:
    contact, created = Contact.objects.get_or_create(
        name=name,
        defaults={
            'company': category,
            'phone': phone,
            'status': 'lead'
        }
    )
    if created:
        Note.objects.create(
            contact=contact,
            body=f"Address: {address}\nRating: {rating}\nReviews: {reviews}\nCategory: {category}"
        )

print(f"Successfully processed {len(leads_data)} leads.")
