# -*- coding: utf-8 -*-

"""
::

    from alkali import Database, Model

    class MyModel( Model ):
        id = fields.IntField(primary_key=True)
        title = fields.StringField()

    db = Database(models=[MyModel], storage=JSONStorage, root_dir='/tmp', save_on_exit=True)

    # create 10 instances and save them
    for i in range(10):
        MyModel(id=i, title='number %d' % i).save()

    assert MyModel.objects.count == 10
    assert MyModel.objects.filter(id__gt=5).count == 4
    assert MyModel.objects.filter(id__gt=5, id__le=7).count == 2
    assert MyModel.objects.get(pk=1).title == 'number 1'
    assert MyModel.objects.order_by('id')[0].id == 0
    assert MyModel.objects.order_by('-id')[0].id == 9
"""

import types
import operator
import collections
import copy
import re

import logging
logger = logging.getLogger(__name__)


class Aggregate(object):
    def __init__(self, field):
        self.field = field

class Count(Aggregate):

    def __call__(self, query):
        return len( query )

class Sum(Aggregate):
    def __call__(self, query):
        return sum( query.values_list(self.field, flat=True) )

class Max(Aggregate):
    def __call__(self, query):
        return max( query.values_list(self.field, flat=True) )

class Min(Aggregate):
    def __call__(self, query):
        return min( query.values_list(self.field, flat=True) )


class Query(object):
    """
    this class performs queries on manager instances
    returns lists of model instances

    this class is one of the main reasons to use alkali

    the Django docs at https://docs.djangoproject.com/en/1.10/topics/db/queries/
    will be fairly relevant to alkali, except for anything related to
    foreign or many2many fields.
    """

    def __init__( self, manager):
        """
        this is an internal class so you shouldn't have to create it directly. create
        via Manager. ``MyModel.objects.filter()``

        :param Manager manager:
        """
        self.manager = manager
        self._instances = manager._instances.values()

    def __len__(self):
        return len(self._instances)

    def __iter__(self):
        return iter(self._instances)

    def __getitem__(self, i):
        return self._instances[i]

    def __str__(self):
        return "<Query: " + ", ".join([str(q) for q in self]) + ">"

    @property
    def count(self):
        """
        **property**: number of model instances we are currently tracking
        """
        return len(self)

    @property
    def instances(self):
        """
        **property**: return our model instances as a list. useful for
        iteration (in a loop) otherwise just index us via ``Query()[n]``

        :rtype: ``list``
        """
        return map( copy.copy, self._instances )

    @property
    def fields(self):
        """
        **property**: helper function to get dict of model fields

        :rtype: ``dict``
        """
        return self.model_class.Meta.fields

    @property
    def model_class(self):
        """
        **property**: return our managers model class
        """
        return self.manager.model_class

    @property
    def field_names(self):
        """
        **property**: return our model field names

        :rtype: ``list`` of ``str``
        """
        return self.fields.keys()

    def all(self):
        return self

    def filter(self, **kw):
        """
        :param kw: ``field_name__op=value``, note: ``field_name`` can be a ``property``
        :rtype: Query

        perform a query, keeping model instances that pass the criteria specified
        in the ``kw`` parameter.

        see example code above. see Django page for very thorough docs on
        this functionality. basically, its field_name '__' operation = value.

        ::

            # field/property f is 'foo' or 'bar'
            MyModel.objects.filter( f__in=['foo','bar'] )

            # 'foo' is in field/property myset
            MyModel.objects.filter( myset__rin='foo' )
        """
        for field, query in kw.iteritems():
            try:
                field, oper = field.split('__')
                oper = oper or 'eq'
            except ValueError: # no __ in field name
                field = field
                oper = 'eq'

            self._instances = self._filter( field, oper, query, self._instances )

        return self

    def _filter(self, field, oper, value, instances):
        """
        helper function that does the actual work of filtering out instances
        """

        def in_(coll, val):
            if not isinstance(coll, types.StringTypes) \
            and isinstance(coll, collections.Iterable):
                return bool( set(coll) & set(val) ) # intersection
            else:
                return coll in val

        def rin_(coll, val):
            if not isinstance(val, types.StringTypes) \
            and isinstance(val, collections.Iterable):
                return bool( set(coll) & set(val) ) # intersection
            else:
                return val in coll

        def regex(coll, val):
            return re.search(val, coll, re.UNICODE)

        def regexi(coll, val):
            return re.search(val, coll, re.UNICODE | re.IGNORECASE)

        if oper == 'in':
            assert isinstance(value, collections.Iterable)
            oper = in_
        elif oper == 'rin':
            assert isinstance(field, collections.Iterable)
            oper = rin_
        elif oper == 're':
            oper = regex
        elif oper == 'rei':
            oper = regexi
        else:
            oper = getattr(operator,oper)
        # TODO: exact, iexact, (i)contains == rin, (i)startswith, (i)endswith,
        # range (for dates), date (return datetime as date), year/month/day,
        # hour/minute/second, week_day (sun=1, sat=7)

        return filter( lambda e: oper(getattr(e,field), value), instances)

    def order_by(self, *fields):
        """
        change order of self.instances

        :param str fields: field names, prefixed with optional '-' to
            indicate reverse order
        :rtype: Query

        **warning**: because this isn't a real database and we don't have
        grouping, passing in multiple fields will very possibly sort
        on the last field only. python sorting is stable however, so a
        multiple field sort may work as intended.
        """
        def _order_by( field ):
            "return reversed, field_name"
            if field.startswith('-'):
                return True, field[1:]
            else:
                return False, field

        if fields == ('pk',):
            fields = self.model_class.Meta.pk_fields.keys()

        for field in fields:
            reverse, field = _order_by( field )
            key = operator.attrgetter(field)
            self._instances = sorted( self._instances, key=key, reverse=reverse)

        return self

    def limit(self, n):
        """
        return first(+) or last(-) n elements

        this has to be the last call during a query since it returns a
        list of instances and not a Query. passing in 0 is a no-op and
        returns all instances

        :param int n: non-zero integer
        :rtype: ``list``
        """
        if n > 0:
            return self._instances[:n]
        elif n < 0:
            return self._instances[n:]
        else: # n == 0, return all instead of [] because why not?
            return self._instances

    def values(self, *fields):
        if not fields:
            fields = self.field_names

        def _mk_dict( obj, fields ):
            vals = [ (field, getattr(obj, field)) for field in fields ]
            return collections.OrderedDict(vals)

        return map( lambda obj: _mk_dict(obj, fields), self._instances )

    def values_list(self, *fields, **kw):
        """
        same as values() but return list instead of a dict
        """
        flat = kw.pop('flat', False)
        assert len(kw) == 0, "extra kwargs passed to values_list"

        if not fields:
            fields = self.field_names

        if flat:
            return [
                getattr(e,field) for field in fields
                for e in self._instances
                ]
        else:
            return [
                [getattr(e,field) for field in fields]
                for e in self._instances
                ]

    def exists(self):
        return len(self) > 0

    def aggregate(self, *args, **kw):
        """
        :param args: ``Count`` ``Sum`` ``Max`` ``Min``
        :param kw: ``field_name=agg``, note: ``field_name`` can be a ``property``
        :rtype: dict

        ::

            MyModel.objects.aggregate( the_count=Count('id'), Sum('size') )
            # { 'the_count': 12, 'size__sum': 24957 }
        """

        ret = {}

        for agg in args:
            key = '{}__{}'.format(agg.field, agg.__class__.__name__.lower())
            ret[key] = agg(self)

        for field, agg in kw.iteritems():
            ret[field] = agg(self)

        return ret
