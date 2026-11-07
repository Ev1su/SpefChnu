from aiogram.filters.callback_data import CallbackData


class AppealStatusCB(CallbackData, prefix="as"):
    appeal_id: int
    status: str


class AppealActionCB(CallbackData, prefix="aa"):
    appeal_id: int
    action: str


class AppealChoiceCB(CallbackData, prefix="ac"):
    appeal_id: int


class JoinStatusCB(CallbackData, prefix="js"):
    application_id: int
    status: str


class JoinActionCB(CallbackData, prefix="ja"):
    application_id: int
    action: str


class JoinEditCB(CallbackData, prefix="je"):
    field: str


class AppealIdentityCB(CallbackData, prefix="ai"):
    share_username: bool


class MyAppealCB(CallbackData, prefix="ma"):
    appeal_id: int
    action: str


class AboutCb(CallbackData, prefix="ab"):
    page: int


AboutCB = AboutCb


class AdminListCB(CallbackData, prefix="al"):
    kind: str
    status: str
    offset: int


class AdminCardCB(CallbackData, prefix="acd"):
    kind: str
    item_id: int
