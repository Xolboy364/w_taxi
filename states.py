from aiogram.fsm.state import StatesGroup, State


class DriverReg(StatesGroup):
    service_type = State()
    car_model = State()
    car_number = State()
    phone = State()
    photo = State()


class DriverMultiRoute(StatesGroup):
    selecting_from = State()
    selecting_from_dist = State()
    selecting_to = State()
    selecting_to_dist = State()


class DriverLocalRoute(StatesGroup):
    pick_region = State()
    pick_from_district = State()
    pick_to_district = State()


class PassengerSearch(StatesGroup):
    from_region = State()
    from_district = State()
    to_region = State()
    to_district = State()


class PassengerOrderState(StatesGroup):
    phone = State()


class AdminManage(StatesGroup):
    add_admin_id = State()
    add_admin_name = State()
    remove_admin_id = State()


class SuperAdminAuth(StatesGroup):
    enter_password = State()


class ChangePasswordState(StatesGroup):
    new_password = State()


class ChangeCardState(StatesGroup):
    new_card_number = State()


class BroadcastState(StatesGroup):
    message_content = State()


class BanUserManage(StatesGroup):
    enter_user_id = State()
    enter_duration = State()
    enter_reason = State()
    unban_user_id = State()


class DriverPaymentState(StatesGroup):
    waiting_receipt = State()


class ServiceAdStates(StatesGroup):
    choose_type = State()
    choose_fuel_types = State()
    enter_name = State()
    enter_location = State()
    enter_phone = State()
    enter_description = State()
    enter_photo = State()
    waiting_payment = State()
    receipt_photo = State()


class RoadsideSearchState(StatesGroup):
    waiting_location = State()


class AdminRejectState(StatesGroup):
    enter_reason = State()


class ComplaintState(StatesGroup):
    enter_text = State()
