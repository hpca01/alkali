from collections import OrderedDict

from .relmanager import RelManager
from .fields import Field, ForeignKey
from . import signals

# from: http://stackoverflow.com/questions/12006267/how-do-django-models-work
# from: lib/python2.7/site-packages/django/db/models/base.py
#
# remember that `type` is actually a class like `str` and `int`
# so you can inherit from it
class MetaModel(type):
    """
    *do not use this class directly*

    *code reviews of this class are vey welcome*

    base class for :class:`alkali.model.Model`. this complicated
    metaclass is required to convert a stylized class into a useful
    concrete one.

    it converts :class:`alkali.fields.Field` variables into their base
    itypes as attributes on the nstantiated class.

    **Meta**: adds a ``Meta`` class if not already defined in ``Model`` derived class

    **objects**: :class:`alkali.manager.Manager`
    """

    # this called once per Model _definition_
    # __new__ is the method called before __init__
    # meta_class is _this_ class, aka: MetaModel
    # this makes a new MetaModel instance
    def __new__(meta_class, name, bases, attrs):
        #print "__new__ cls:",type(meta_class),meta_class,name
        super_new = super(MetaModel, meta_class).__new__

        # Also ensure initialization is only performed for subclasses of Model
        # (excluding Model class itself). This keeps all of Models attrs intact.
        if not any( map( lambda b: isinstance(b, MetaModel), bases ) ):
            new_class = super_new(meta_class, name, bases, attrs)
            return new_class

        # new_class is an instance of 'name' (aka Model) whose type is MetaModel
        # print "new_class", type(new_class), new_class
        # new_class <class 'alkali.metamodel.MetaModel'> <class 'redb.metamodel.MyModel'>
        new_class = super_new(meta_class, name, bases, {})
        new_class._add_meta( attrs )
        new_class._add_manager()
        new_class._add_relmanagers()

        # put the rest of the attributes (methods and properties)
        # defined in the Model derived class into the "new" Model
        for name, attr in attrs.items():
            setattr(new_class, name, attr)

        signals.model_creation.send(meta_class, model=new_class)

        return new_class

    def _add_manager( new_class ):
        from .manager import Manager
        setattr( new_class, 'objects', Manager(new_class) )

    def _add_relmanagers( new_class ):
        """
        if this class has foreign keys then we need to add the
        reverse lookup into the *other* model
        """
        for name, field in new_class.Meta.fields.items():
            if not isinstance(field, ForeignKey):
                continue

            # note the name=name in the lambda, this is vital to capture
            # the current value of name and not the last of the loop
            # more info: http://stackoverflow.com/questions/2295290
            rel_manager = property(
                    lambda fm_instance, name=name: RelManager(fm_instance, new_class, name)
                    )
            set_name = "{}_set".format(new_class.__name__).lower()

            setattr( field.foreign_model, set_name, rel_manager )

    def _add_meta( new_class, attrs ):

        def _get_fields( attrs ):
            return [(k,v) for k,v in attrs.items() if isinstance(v,Field)]

        def _get_field_order(attrs):
            """
            returns field names in the order they were defined in the class
            """
            fields = _get_fields(attrs)
            fields.sort(key=lambda e: e[1]._order)
            return [k for k, _ in fields]

        class Object(object): pass

        meta = attrs.pop( 'Meta', Object )
        setattr( new_class, 'Meta', meta() )

        if not hasattr(meta, 'filename'):
            meta.filename = None

        if not hasattr(meta, 'storage'):
            meta.storage = None

        if not hasattr(meta, 'ordering'):
            meta.ordering = _get_field_order(attrs)

        meta.field_filter = lambda self, field_type: \
                [n for n,f in self.fields.items() if isinstance(f, field_type)]

        # don't let user miss a field if they've defined Meta.ordering
        assert len(meta.ordering) == len(_get_fields(attrs)), \
            "missing/extra fields defined in Meta.ordering"

        # meta.ordering contains field names, attrs contains Field types
        meta.fields = OrderedDict()
        for field in meta.ordering:
            meta.fields[field] = attrs.pop(field)
            delattr( meta.fields[field], '_order' )

        # make sure 'pk' isn't a field name, etc
        for d in dir(new_class):
            assert d not in meta.fields

        # you can set a property on a class but it will only be called on an instance
        # I'd prefer this to be a read-only property but I guess that can't happen
        #
        # note: don't use a dict comprehension because interim dict will have keys
        # inserted in random order
        meta.pk_fields = OrderedDict(
                [(name,field) for name,field in meta.fields.items() if field.primary_key]
                )

        if len(meta.fields):
            assert len(meta.pk_fields) > 0, "no primary_key defined in fields"


    # creates a new instance of derived model, this is called each
    # time a Model instance is created
    def __call__(cls, *args, **kw):
        obj = cls.__new__(cls, *args)

        # put fields into model instance
        for name in cls.Meta.fields.iterkeys():
            value = kw.pop(name, None)
            value = obj.Meta.fields[name].cast(value)
            setattr(obj, name, value)

        setattr( obj, '_dirty', False )

        obj.__init__(*args, **kw)

        return obj
