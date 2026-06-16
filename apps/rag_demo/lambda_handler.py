from mangum import Mangum

from apps.rag_demo.main import app

handler = Mangum(app, lifespan="off")
