import environ

env = environ.FileAwareEnv()

WAFFLE_CREATE_MISSING_FLAGS = True
WAFFLE_CREATE_MISSING_SWITCHES = True
WAFFLE_CREATE_MISSING_SAMPLES = True
WAFFLE_FLAG_DEFAULT = env("WAFFLE_FLAG_DEFAULT", default=True)
