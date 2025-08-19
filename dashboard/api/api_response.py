import logging
from http import HTTPStatus

logger = logging.getLogger(__name__)

Response = tuple[dict, int]

class ApiResponse:

    @staticmethod
    def success(data = None, status: HTTPStatus = HTTPStatus.OK) -> Response:
        '''
        Returns a success response with the given data.

        :param data: The data to return in the response
        :return: A dictionary containing the success response
        '''
        return {'success': True, 'data': data}, int(status)

    @staticmethod
    def error(message: str, status: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR, exc_info: bool = False) -> Response:
        '''
        Returns an error response with the given message. Also logs the error.

        :param message: The error message to return
        :param exc_info: If True, includes exception information in the log (can be only used in except blocks)
        :return: A dictionary containing the error response
        '''
        logger.error(message, exc_info=exc_info)
        return {'success': False, 'message': message}, int(status)
