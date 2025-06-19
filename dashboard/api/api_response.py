class ApiResponse:

    @staticmethod
    def success(data = None) -> dict:
        return {'success': True, 'data': data}

    @staticmethod
    def error(message: str) -> dict:
        return {'success': False, 'message': message}
