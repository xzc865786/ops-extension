from enum import StrEnum


class TicketCategory(StrEnum):
    API_ERROR = "API_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    BILLING_ERROR = "BILLING_ERROR"
    RECHARGE_PAYMENT = "RECHARGE_PAYMENT"
    INVOICE = "INVOICE"
    REFUND = "REFUND"
    MODEL_AVAILABILITY = "MODEL_AVAILABILITY"
    RATE_LIMIT = "RATE_LIMIT"
    ACCOUNT = "ACCOUNT"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    OTHER = "OTHER"


class TicketPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    WAITING_USER = "WAITING_USER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ClosedBy(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class TicketEventType(StrEnum):
    CREATED = "CREATED"
    CLAIMED = "CLAIMED"
    UNCLAIMED = "UNCLAIMED"
    TAKEN_OVER = "TAKEN_OVER"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    CATEGORY_CHANGED = "CATEGORY_CHANGED"
    USER_REPLIED = "USER_REPLIED"
    ADMIN_REPLIED = "ADMIN_REPLIED"
    INTERNAL_NOTE_ADDED = "INTERNAL_NOTE_ADDED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    CLOSED_BY_USER = "CLOSED_BY_USER"
    CLOSED_BY_ADMIN = "CLOSED_BY_ADMIN"
    REF_TICKET_LINKED = "REF_TICKET_LINKED"


class ExpenseStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class ExpenseCategory(StrEnum):
    CLOUD_SERVER = "CLOUD_SERVER"
    GPU_COMPUTE = "GPU_COMPUTE"
    MODEL_API = "MODEL_API"
    SOFTWARE_SUB = "SOFTWARE_SUB"
    DOMAIN = "DOMAIN"
    CDN = "CDN"
    OBJECT_STORAGE = "OBJECT_STORAGE"
    SMS_EMAIL = "SMS_EMAIL"
    OFFICE = "OFFICE"
    STAFF_ADVANCE = "STAFF_ADVANCE"
    MARKETING = "MARKETING"
    PROXY_NETWORK = "PROXY_NETWORK"
    HARDWARE = "HARDWARE"
    TECH_SERVICE = "TECH_SERVICE"
    TAX_SERVICE = "TAX_SERVICE"
    OTHER = "OTHER"


class PayType(StrEnum):
    COMPANY_DIRECT = "COMPANY_DIRECT"
    PERSONAL_ADVANCE = "PERSONAL_ADVANCE"


class PaymentAccountType(StrEnum):
    COMPANY_BANK = "COMPANY_BANK"
    ALIPAY = "ALIPAY"
    WECHAT = "WECHAT"
    PERSONAL_BANK = "PERSONAL_BANK"
    OTHER = "OTHER"


class InvoiceStatus(StrEnum):
    NONE = "NONE"
    PENDING = "PENDING"
    RECEIVED = "RECEIVED"
    NOT_REQUIRED = "NOT_REQUIRED"


class InvoiceType(StrEnum):
    VAT_SPECIAL = "VAT_SPECIAL"
    VAT_NORMAL = "VAT_NORMAL"
    RECEIPT = "RECEIPT"
    OTHER = "OTHER"


class ExpenseAttachmentType(StrEnum):
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"
    CONTRACT = "CONTRACT"
    PAYMENT_SCREENSHOT = "PAYMENT_SCREENSHOT"
    BANK_SLIP = "BANK_SLIP"
    OTHER = "OTHER"


class ExpenseEventType(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    PAYMENT_ADDED = "PAYMENT_ADDED"
    PAID = "PAID"
    INVOICE_ADDED = "INVOICE_ADDED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    PAYMENT_RECONCILED = "PAYMENT_RECONCILED"


TICKET_STATUS_TRANSITIONS = {
    TicketStatus.OPEN: {TicketStatus.PROCESSING, TicketStatus.WAITING_USER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.PROCESSING: {TicketStatus.WAITING_USER, TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.OPEN},
    TicketStatus.WAITING_USER: {TicketStatus.PROCESSING, TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.OPEN},
    TicketStatus.RESOLVED: {TicketStatus.CLOSED, TicketStatus.PROCESSING},
    TicketStatus.CLOSED: set(),
}

EXPENSE_CATEGORY_LABELS = {
    ExpenseCategory.CLOUD_SERVER: "云服务器",
    ExpenseCategory.GPU_COMPUTE: "GPU 算力",
    ExpenseCategory.MODEL_API: "模型 API",
    ExpenseCategory.SOFTWARE_SUB: "软件订阅",
    ExpenseCategory.DOMAIN: "域名",
    ExpenseCategory.CDN: "CDN",
    ExpenseCategory.OBJECT_STORAGE: "对象存储",
    ExpenseCategory.SMS_EMAIL: "短信/邮件",
    ExpenseCategory.OFFICE: "办公",
    ExpenseCategory.STAFF_ADVANCE: "员工垫付",
    ExpenseCategory.MARKETING: "市场推广",
    ExpenseCategory.PROXY_NETWORK: "代理/网络",
    ExpenseCategory.HARDWARE: "硬件",
    ExpenseCategory.TECH_SERVICE: "技术服务",
    ExpenseCategory.TAX_SERVICE: "税务服务",
    ExpenseCategory.OTHER: "其他",
}

COST_CENTER_SEEDS = [
    ("API_PLATFORM", "API 平台"),
    ("INFRA", "服务器基础设施"),
    ("MODEL_PROCUREMENT", "模型采购"),
    ("OPERATIONS", "运营"),
    ("RND", "研发"),
    ("ADMIN", "行政"),
    ("OTHER", "其他"),
]

TICKET_CATEGORY_LABELS = {
    TicketCategory.API_ERROR: "API 错误",
    TicketCategory.AUTH_ERROR: "认证错误",
    TicketCategory.BILLING_ERROR: "计费错误",
    TicketCategory.RECHARGE_PAYMENT: "充值/支付",
    TicketCategory.INVOICE: "发票",
    TicketCategory.REFUND: "退款",
    TicketCategory.MODEL_AVAILABILITY: "模型可用性",
    TicketCategory.RATE_LIMIT: "限流",
    TicketCategory.ACCOUNT: "账户",
    TicketCategory.FEATURE_REQUEST: "功能建议",
    TicketCategory.OTHER: "其他",
}
