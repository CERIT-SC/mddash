import logging
from http import HTTPStatus
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

Response = tuple[dict, int]

class ApiResponse:

    @staticmethod
    def success(data = None, status: HTTPStatus | int | None = None) -> Response:
        '''
        Returns a success response with the given data.

        :param data: The data to return in the response
        :return: A dictionary containing the success response
        '''
        if status is None:
            status = HTTPStatus.OK

        return {'success': True, 'data': data}, int(status)

    @staticmethod
    def error(error: Exception | str, status: HTTPStatus | int | None = None) -> Response:
        '''
        Returns an error response with the given message. Also logs the error.

        :param message: The error message to return
        :param exc_info: If True, includes exception information in the log (can be only used in except blocks)
        :return: A dictionary containing the error response
        '''
        exc_info = True

        if isinstance(error, HTTPException):
            status = error.code or status
            message = error.get_description()
        elif isinstance(error, Exception):
            message = str(error)
        else:
            message = error
            exc_info = False

        if status is None:
            status = HTTPStatus.INTERNAL_SERVER_ERROR

        logger.error(message, exc_info=exc_info)
        return {'success': False, 'message': message}, int(status)
