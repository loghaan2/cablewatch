import tomllib
import os
import hashlib
import binascii
import re
import getpass
from loguru import logger
from cablewatch import config


class User:
    DEFAULT_ROLES = ''
    DEFAULT_PASSWORD_HASH = None
    PBKDF2_ITERATIONS = 100000

    def __init__(self, name):
        self._name = name
        self.reload()

    def reset(self):
        self._error_msg = None
        self._roles = self.DEFAULT_ROLES
        self._password_hash = self.DEFAULT_PASSWORD_HASH

    def __repr__(self):
        s = f'<{self.__class__.__name__}'
        for k,v in self.__dict__.items():
            s += f' {k[1:]}={v!r}'
        s += '>'
        return s

    @property
    def roles(self):
        return self._roles.split()

    @property
    def name(self):
        return self._name

    def reload(self):
        self.reset()
        conf = config.Config()
        with open(f"{conf.PROJECT_DIR}/cablewatch-local.toml", "rb") as f:
            d = tomllib.load(f)
            if 'users' not in d:
                return
            for user in d['users']:
                if user.get('name', None) == self._name:
                    self._password_hash = user.get('password_hash', self.DEFAULT_PASSWORD_HASH)
                    if self._password_hash != self.DEFAULT_PASSWORD_HASH:
                        self._password_hash = str(self._password_hash).encode('utf-8')
                    self._roles = str(user.get('roles', self.DEFAULT_ROLES))
                    self.checkFields()
                    return
        self._error_msg = f'there is no user named {self._name!r}'

    def checkFields(self):
        if not isinstance(self._name, str) or not re.match(r'[A-Za-z_]+', self._name):
            self._error_msg = f'invalid user name {self._name!r}'
            return
        if not isinstance(self._roles, str) or not re.match(r'[A-Za-z_ ]*', self._roles):
            self._error_msg = f'invalid user roles {self._roles!r}'
            return
        if not isinstance(self._password_hash, bytes) or not re.match(rb'[0-9a-f]*', self._password_hash):
            self._error_msg = f'invalid password hash {self._password_hash!r}'
            return

    def verifyPassword(self, provided_password, *, log=True):
        if self._error_msg:
            if log:
                logger.warning(f"cannot auth. because {self._error_msg}")
            return False
        stored_hashed_password = self._password_hash
        salt = stored_hashed_password[:64]
        stored_hashed_password = stored_hashed_password[64:]
        provided_hashed_password = hashlib.pbkdf2_hmac('sha512', provided_password.encode('utf-8'), salt, self.PBKDF2_ITERATIONS)
        provided_hashed_password = binascii.hexlify(provided_hashed_password)
        if provided_hashed_password==stored_hashed_password:
            if log:
                logger.warning(f"user {self._name!r} authentificated")
            return True
        else:
            if log:
                logger.warning(f"invalid password for {self._name!r}")
            return False

    def generatePasswordHash(self, password):
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
        hashed_password = hashlib.pbkdf2_hmac('sha512', password.encode('utf8'), salt, self.PBKDF2_ITERATIONS)
        hashed_password = binascii.hexlify(hashed_password)
        hashed_password = salt + hashed_password
        return hashed_password.decode('utf-8')

    def generateTomlSection(self, password, roles):
        password_hash = self.generatePasswordHash(password)
        s = ''
        s += '[[users]]\n'
        s += f'name = "{self._name}"\n'
        s += f'password_hash = "{password_hash}"\n'
        s += f'roles = "{roles}"\n'
        s += '\n'
        return s


def main():
    name = input("Username: ")
    password = getpass.getpass("Password: ")
    roles = input("Roles: ")
    user = User(name)
    print()
    print("Just copy the content below to your cablewatch-local.toml:")
    print()
    print(user.generateTomlSection(password, roles))
