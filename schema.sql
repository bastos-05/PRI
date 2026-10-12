CREATE TABLE articles (
    page_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE categories (
    name TEXT PRIMARY KEY,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    depth INTEGER NOT NULL
);

CREATE TABLE belongs_to (
    page_id INTEGER NOT NULL,
    category_name TEXT NOT NULL,

    PRIMARY KEY (page_id, category_name),

    FOREIGN KEY (page_id) REFERENCES articles(page_id),
    FOREIGN KEY (category_name) REFERENCES categories(name)
);

CREATE TABLE category_edges (
    parent_name TEXT NOT NULL,
    child_name TEXT NOT NULL,

    PRIMARY KEY (parent_name, child_name),

    FOREIGN KEY (parent_name) REFERENCES categories(name),
    FOREIGN KEY (child_name) REFERENCES categories(name)
);