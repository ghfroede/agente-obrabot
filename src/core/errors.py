class ObrabotError(Exception):
    """Erro base da aplicação."""


class NotFoundError(ObrabotError):
    pass


class ValidationError(ObrabotError):
    pass


class UnauthorizedError(ObrabotError):
    pass


class ForbiddenError(ObrabotError):
    pass


class RateLimitError(ObrabotError):
    pass


class BucketConflictError(ObrabotError):
    """Documento final já existe no bucket."""


class ApprovalRequiredError(ObrabotError):
    pass


class AdminLoginRequired(ObrabotError):
    """Sessão de admin ausente — exige redirect para o login do painel."""
