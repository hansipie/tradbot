CREATE TABLE IF NOT EXISTS trades (
    id             SERIAL      PRIMARY KEY,
    symbol         TEXT        NOT NULL,
    side           TEXT        NOT NULL,
    price          NUMERIC     NOT NULL,
    amount         NUMERIC     NOT NULL,
    capital_after  NUMERIC     NOT NULL,
    position_after NUMERIC     NOT NULL,
    reason         TEXT,
    ts             TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS equity (
    ts             TIMESTAMPTZ PRIMARY KEY,
    capital        NUMERIC     NOT NULL,
    position_value NUMERIC     NOT NULL,
    total          NUMERIC     NOT NULL
);
