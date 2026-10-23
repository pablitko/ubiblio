BEGIN TRANSACTION;
CREATE TABLE "bookImages" (
	id INTEGER NOT NULL, 
	"bookId" INTEGER, 
	filename VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY("bookId") REFERENCES books (id)
);
CREATE TABLE books (
	id INTEGER NOT NULL, 
	title VARCHAR, 
	author VARCHAR, 
	summary VARCHAR, 
	genre VARCHAR, 
	library VARCHAR, 
	shelf VARCHAR, 
	collection VARCHAR, 
	"ISBN" VARCHAR, 
	notes VARCHAR, 
	owned BOOLEAN, 
	withdrawn BOOLEAN, 
	"withdrawnBy" VARCHAR, 
	"customField1" VARCHAR, 
	"customField2" VARCHAR, 
	ebook BOOLEAN, 
	PRIMARY KEY (id)
);
INSERT INTO "books" VALUES(1,'Lalka','Bolesław Prus',NULL,'Classic',NULL,'A1',NULL,'9788377792094',NULL,1,0,NULL,NULL,NULL,0);
INSERT INTO "books" VALUES(2,'Solaris','Stanisław Lem',NULL,NULL,NULL,'A2',NULL,'830802534X',NULL,1,0,NULL,'pierwsze wydanie',NULL,0);
INSERT INTO "books" VALUES(3,'Zażółć gęślą jaźń',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'pożyczona',1,1,'ania',NULL,NULL,0);
CREATE TABLE config (
	id INTEGER NOT NULL, 
	version VARCHAR, 
	"coverImages" BOOLEAN, 
	"customFieldName1" VARCHAR, 
	"customFieldName2" VARCHAR, 
	genres VARCHAR, 
	PRIMARY KEY (id)
);
INSERT INTO "config" VALUES(1,'1.0.1',0,'','','Sci-Fi,Fantasy,Classic,Reference,Young Adult,Historical Fiction,Mystery,Anthology,Horror,Romance,Animal Fiction');
CREATE TABLE ebooks (
	id INTEGER NOT NULL, 
	"bookId" INTEGER, 
	filename VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY("bookId") REFERENCES books (id)
);
CREATE TABLE links (
	id INTEGER NOT NULL, 
	"accessCode" VARCHAR, 
	validity DATETIME DEFAULT (CURRENT_TIMESTAMP), 
	PRIMARY KEY (id)
);
CREATE TABLE readinglistitems (
	id INTEGER NOT NULL, 
	book INTEGER, 
	user_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(book) REFERENCES books (id)
);
CREATE TABLE "userEmails" (
	id INTEGER NOT NULL, 
	email VARCHAR, 
	user_id INTEGER, 
	PRIMARY KEY (id)
);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR, 
	passhash VARCHAR, 
	"isAdmin" BOOLEAN, 
	PRIMARY KEY (id)
);
CREATE TABLE vkeys (
	id INTEGER NOT NULL, 
	vkey VARCHAR, 
	url VARCHAR, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX "ix_links_accessCode" ON links ("accessCode");
CREATE INDEX ix_vkeys_url ON vkeys (url);
CREATE INDEX ix_vkeys_vkey ON vkeys (vkey);
COMMIT;
