from django.db import migrations


PERMISOS = [
    ('preparar_pedido', 'Puede preparar pedidos'),
    ('entregar_pedido', 'Puede confirmar entregas de pedidos'),
    ('cancelar_pedido', 'Puede cancelar pedidos'),
]


def separar_permisos(apps, schema_editor):
    alias = schema_editor.connection.alias
    tipo = apps.get_model('contenttypes', 'ContentType').objects.using(alias).filter(
        app_label='pedidos', model='pedido',
    ).first()
    if not tipo:
        return  # En una instalación nueva los permisos se generan al terminar migrate.
    permisos = apps.get_model('auth', 'Permission').objects.using(alias)
    anterior = permisos.filter(content_type=tipo, codename='cambiar_estado_pedido').first()
    if not anterior:
        return
    nuevos = [
        permisos.get_or_create(content_type=tipo, codename=codigo, defaults={'name': nombre})[0]
        for codigo, nombre in PERMISOS
    ]
    grupos = apps.get_model('auth', 'Group').objects.using(alias).filter(permissions=anterior)
    usuarios = apps.get_model('seguridad', 'Usuario').objects.using(alias).filter(user_permissions=anterior)
    for grupo in grupos:
        grupo.permissions.add(*nuevos)
    for usuario in usuarios:
        usuario.user_permissions.add(*nuevos)
    anterior.delete(using=alias)


class Migration(migrations.Migration):
    dependencies = [
        ('pedidos', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='pedido',
            options={'ordering': ['-fecha_creacion'], 'permissions': PERMISOS,
                     'verbose_name': 'pedido', 'verbose_name_plural': 'pedidos'},
        ),
        migrations.RunPython(separar_permisos),
    ]
