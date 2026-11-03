os.environ.update(DATABASE_URL="postgresql+psycopg://postgres@/sd?host=/tmp&port=5433",JWT_SECRET_KEY="x"*40,FLASK_ENV="development",JWT_TOKEN_LOCATION='["cookies","headers"]')
import config
config.Config.SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"]
