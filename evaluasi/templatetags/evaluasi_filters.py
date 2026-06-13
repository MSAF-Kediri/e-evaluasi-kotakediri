from django import template

register = template.Library()

@register.filter(name='dict_get')
def dict_get(dictionary, key):
    """Filter untuk mengambil nilai dictionary berdasarkan dynamic key di template"""
    if dictionary:
        # Paksa key menjadi string atau integer sesuai tipe data key di jawaban_map Anda
        return dictionary.get(key) or dictionary.get(str(key)) or dictionary.get(int(key) if isinstance(key, str) and key.isdigit() else key)
    return None

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)