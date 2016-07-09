from redb.model import Model
from redb import fields

class EmptyModel(Model):
    pass

class MyModel( Model ):
    class Meta:
        ordering = ['int_type','str_type','dt_type']

    int_type = fields.IntField(primary_key=True)
    str_type = fields.StringField()
    dt_type  = fields.DateField()
