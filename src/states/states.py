from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Create your states here.
class RegStatet(StatesGroup):
    waiting_for_name = State()