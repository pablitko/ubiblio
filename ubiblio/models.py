from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from .database import Base
from sqlalchemy.sql import func
from datetime import datetime, timezone

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    passhash = Column(String)
    isAdmin = Column(Boolean, default=False)

class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    author = Column(String)
    summary = Column(String)
    genre = Column(String)
    library = Column(String)
    shelf = Column(String)
    collection = Column(String)
    ISBN = Column(String)
    notes = Column(String, nullable=True)
    owned = Column(Boolean)
    withdrawn = Column(Boolean)
    withdrawnBy = Column(String, nullable=True)
    customField1 = Column(String, nullable=True)
    customField2 = Column(String, nullable=True)
    ebook = Column(Boolean,nullable=True, default=False)
    # Added in DB version 1.1.0. Dates are naive UTC (SQLite CURRENT_TIMESTAMP is UTC too).
    dateAdded = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), server_default=func.now())
    lastVerified = Column(DateTime, nullable=True)
    publisher = Column(String, nullable=True)
    publishedYear = Column(Integer, nullable=True)
    pages = Column(Integer, nullable=True)
    language = Column(String, nullable=True)

class readingListItems(Base):
    __tablename__ = "readinglistitems"
    id = Column(Integer, primary_key=True)
    book = Column(Integer, ForeignKey("books.id"))
    user_id = Column(Integer)
    
class bookImage(Base):
    __tablename__ = "bookImages"
    id = Column(Integer, primary_key=True)
    bookId = Column(Integer, ForeignKey("books.id"))
    filename = Column(String, nullable=False)  

class config(Base):
    __tablename__= "config"
    id = Column(Integer, primary_key=True)
    version = Column(String)
    coverImages = Column(Boolean)
    customFieldName1 = Column(String, nullable=True)
    customFieldName2 = Column(String, nullable=True)
    genres = Column(String)

class ebook(Base):
    __tablename__ = "ebooks"
    id = Column(Integer, primary_key=True)
    bookId = Column(Integer, ForeignKey("books.id"))
    filename = Column(String, nullable=False) 

class emails(Base):
    __tablename__ = "userEmails"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=True)
    user_id = Column(Integer)
    
class link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True)
    accessCode = Column(String, index=True)
    validity = Column(DateTime(timezone=True), server_default=func.now())
    
class vkey(Base):
    __tablename__ = "vkeys"
    id = Column(Integer, primary_key=True)
    vkey = Column(String, index=True)
    url = Column(String, index=True)
    
    
