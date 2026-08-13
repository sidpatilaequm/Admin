import sys
import os
import django

# Add the project directory to PYTHONPATH
sys.path.append("D:/Invoika_Django_v1.1.0/Admin/pages/admin.py")

# Set Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "invoika.settings")

# Initialize Django
django.setup()
