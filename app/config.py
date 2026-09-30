"""Local settings; connection credentials never belong in a response or log."""
import os
import re

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    uri: SecretStr = Field(repr=False)
    database: str

    @field_validator('uri')
    @classmethod
    def valid_uri(cls, value):
        if not value.get_secret_value().startswith(('mongodb://', 'mongodb+srv://')):
            raise ValueError('MONGODB_URI must be a MongoDB connection string')
        return value

    @field_validator('database')
    @classmethod
    def valid_database(cls, value):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,63}', value) or value.lower() in {'admin', 'local', 'config'}:
            raise ValueError('Choose a non-system database name using letters, digits, underscores or hyphens')
        return value

    @classmethod
    def from_env(cls):
        load_dotenv('.env')
        uri, database = os.getenv('MONGODB_URI'), os.getenv('MONGODB_DATABASE')
        if not uri or not database:
            raise ValueError('Set MONGODB_URI and MONGODB_DATABASE in the environment or local .env')
        return cls(uri=uri, database=database)
