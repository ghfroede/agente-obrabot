class ObrabotError(Exception):
    """Erro base da aplicação."""


class NotFoundError(ObrabotError):
    pass


class ValidationError(ObrabotError):
    pass


class UnauthorizedError(ObrabotError):
    pass


class BucketConflictError(ObrabotError):
    """Documento final já existe no bucket."""


class ApprovalRequiredError(ObrabotError):
    pass
