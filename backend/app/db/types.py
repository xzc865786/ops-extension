
from sqlalchemy import BigInteger, Integer

BigIntPK = BigInteger().with_variant(Integer, "sqlite")
BigInt = BigInteger().with_variant(Integer, "sqlite")
