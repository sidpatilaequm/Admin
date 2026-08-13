from django.core.management.base import BaseCommand
from pages.models import Material, Attribute

class Command(BaseCommand):
    help = 'Populate database with demo data for variant system'

    def handle(self, *args, **options):
        self.stdout.write('Creating demo data...')
        
        # Create sample attributes
        attributes_data = [
            {'name': 'Color', 'type': 'VARIANT'},
            {'name': 'Size', 'type': 'VARIANT'},
            {'name': 'Material', 'type': 'VARIANT'},
            {'name': 'Sleeve Type', 'type': 'VARIANT'},
            {'name': 'Wash Care', 'type': 'GENERAL'},
            {'name': 'Country of Origin', 'type': 'GENERAL'},
        ]
        
        for attr_data in attributes_data:
            attribute, created = Attribute.objects.get_or_create(
                name=attr_data['name'],
                defaults=attr_data
            )
            if created:
                self.stdout.write(f'Created attribute: {attribute.name}')
        
        # Create sample materials
        materials_data = [
            {
                'material_code': 'SHIRT001',
                'material_name': 'Cotton Shirt',
                'sku': 'SHIRT001',
                'material_type': 'FERT',
                'category': 'Apparel',
                'subcategory': 'Shirts',
                'description': 'Comfortable cotton shirt with various style options',
                'price': 599.00,
                'current_stock': 100,
            },
            {
                'material_code': 'PANT002',
                'material_name': 'Denim Jeans',
                'sku': 'PANT002',
                'material_type': 'FERT',
                'category': 'Apparel',
                'subcategory': 'Pants',
                'description': 'Classic denim jeans with multiple fits',
                'price': 899.00,
                'current_stock': 75,
            },
            {
                'material_code': 'SHOE003',
                'material_name': 'Running Shoes',
                'sku': 'SHOE003',
                'material_type': 'FERT',
                'category': 'Footwear',
                'subcategory': 'Sports',
                'description': 'Comfortable running shoes for daily use',
                'price': 1299.00,
                'current_stock': 50,
            },
        ]
        
        for material_data in materials_data:
            material, created = Material.objects.get_or_create(
                material_code=material_data['material_code'],
                defaults=material_data
            )
            if created:
                self.stdout.write(f'Created material: {material.material_name}')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created demo data!')
        )
        self.stdout.write('You can now access:')
        self.stdout.write('- Variant Matrix: /variants/matrix/')
        self.stdout.write('- Variant List: /variants/') 