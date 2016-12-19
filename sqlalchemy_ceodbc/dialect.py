# sqlalchemy_ceodbc/dialect.py
# Copyright (C) 2016 Dirk Jonker
#
# This module is released under
# the MIT License: https://opensource.org/licenses/MIT
#
# Adapted from SQLAlchemy
# dialects/mssql/pyodbc.py
# Copyright (C) 2005-2016 the SQLAlchemy authors and contributors

"""
.. dialect:: mssql+ceodbc
    :name: ceODBC
    :dbapi: ceODBC
    :connectstring: mssql+ceodbc://<username>:<password>@<dsnname>
    :url: http://ceodbc.readthedocs.org/
"""

from sqlalchemy.dialects.mssql.base import MSExecutionContext, MSDialect
from .connector import ceODBCConnector
from sqlalchemy import exc
import re


class MSExecutionContext_ceodbc(MSExecutionContext):
    _embedded_scope_identity = False

    def create_cursor(self):
        """Set the arraysize to 100 by default to speed up fetchmany's."""
        c = self._dbapi_connection.cursor()
        c.arraysize = 100
        return c

    def pre_exec(self):
        """where appropriate, issue "select scope_identity()" in the same
        statement.

        Background on why "scope_identity()" is preferable to "@@identity":
        http://msdn.microsoft.com/en-us/library/ms190315.aspx

        Background on why we attempt to embed "scope_identity()" into the same
        statement as the INSERT:
        http://code.google.com/p/pyodbc/wiki/FAQs#How_do_I_retrieve_autogenerated/identity_values?

        """

        super(MSExecutionContext_ceodbc, self).pre_exec()

        # don't embed the scope_identity select into an
        # "INSERT .. DEFAULT VALUES"
        if self._select_lastrowid and \
                self.dialect.use_scope_identity and \
                len(self.parameters[0]):
            self._embedded_scope_identity = True

            self.statement += "; select scope_identity()"

    def post_exec(self):
        if self._embedded_scope_identity:
            # Fetch the last inserted id from the manipulated statement
            # We may have to skip over a number of result sets with
            # no data (due to triggers, etc.)
            while True:
                try:
                    # fetchall() ensures the cursor is consumed
                    # without closing it (FreeTDS particularly)
                    row = self.cursor.fetchall()[0]
                    break
                except self.dialect.dbapi.Error as e:
                    # no way around this - nextset() consumes the previous set
                    # so we need to just keep flipping
                    self.cursor.nextset()

            self._lastrowid = int(row[0])
        else:
            super(MSExecutionContext_ceodbc, self).post_exec()


class MSDialect_ceODBC(ceODBCConnector, MSDialect):

    default_paramstyle = 'qmark'

    execution_ctx_cls = MSExecutionContext_ceodbc

    def __init__(self, description_encoding=None, **params):
        if 'description_encoding' in params:
            self.description_encoding = params.pop('description_encoding')
        super(MSDialect_ceODBC, self).__init__(**params)
        self.use_scope_identity = self.use_scope_identity and \
            self.dbapi and \
            hasattr(self.dbapi.Cursor, 'nextset')

    def do_executemany(self, cursor, statement, parameters, context=None):
        cursor.executemany(statement, list(parameters))

    def _get_server_version_info(self, connection):
        try:
            raw = connection.scalar("SELECT  SERVERPROPERTY('ProductVersion')")
        except exc.DBAPIError:
            # SQL Server docs indicate this function isn't present prior to
            # 2008; additionally, unknown combinations of drivers aren't
            # able to run this query.
            return (13, 0, 0)
        else:
            version = []
            r = re.compile('[.\-]')
            for n in r.split(raw):
                try:
                    version.append(int(n))
                except ValueError:
                    version.append(n)
            return tuple(version)
