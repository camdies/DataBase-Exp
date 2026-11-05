from decimal import Decimal, InvalidOperation


class Problem(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def integer(value, name, minimum=1, maximum=2147483647):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise Problem(422, 'INVALID_INPUT', f'{name} 必须为整数')
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise Problem(422, 'INVALID_INPUT', f'{name} 必须为整数')
    if not minimum <= result <= maximum:
        raise Problem(422, 'INVALID_INPUT', f'{name} 超出允许范围')
    return result


def string(value, name, maximum):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise Problem(422, 'INVALID_INPUT', f'{name} 不能为空且不能超过 {maximum} 字符')
    return value.strip()


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or not 0 < result <= Decimal('99999999.99') or result != result.quantize(Decimal('.01')):
            raise InvalidOperation()
        return result
    except (InvalidOperation, ValueError):
        raise Problem(422, 'INVALID_INPUT', '价格必须为正数，最多两位小数')


def authorize(actor, admin=False):
    if not actor or actor.get('role') not in (['admin'] if admin else ['admin', 'clerk']):
        raise Problem(403, 'FORBIDDEN', '当前账户没有此操作权限')
