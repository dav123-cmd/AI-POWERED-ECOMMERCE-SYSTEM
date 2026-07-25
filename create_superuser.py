import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ShopSmartAI.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
first_name = os.environ.get("DJANGO_SUPERUSER_FIRST_NAME", "Admin")
last_name = os.environ.get("DJANGO_SUPERUSER_LAST_NAME", "User")

if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(email=email,password=password,first_name=first_name,last_name=last_name,
    )
    print("Superuser created successfully")
else:
    print("Superuser already exists")