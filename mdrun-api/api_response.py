import logging
from http import HTTPStatus
from flask import jsonify, Response
from werkzeug.exceptions import HTTPException


logger = logging.getLogger(__name__)


class ApiResponse:

    @staticmethod
    def success(data=None, status: HTTPStatus | int | None = None) -> Response:
        '''
        Returns a success response with the given data.

        :param data: The data to return in the response
        :param status: The HTTP status code (defaults to 200 OK)
        :return: A Flask Response object containing the success response
        '''
        if status is None:
            status = HTTPStatus.OK

        response_data = {'success': True, 'data': data}
        response = jsonify(response_data)
        response.status_code = int(status)
        return response

    @staticmethod
    def error(error: Exception | str, status: HTTPStatus | int | None = None) -> Response:
        '''
        Returns an error response with the given message. Also logs the error.

        :param error: The error message or exception to return
        :param status: The HTTP status code (defaults to 500 Internal Server Error)
        :return: A Flask Response object containing the error response
        '''
        exc_info = False

        if isinstance(error, HTTPException):
            status = error.code or status
            message = error.description or "Unknown error occurred."
        elif isinstance(error, Exception):
            message = str(error)
            exc_info = True
        else:
            message = error

        if status is None:
            status = HTTPStatus.INTERNAL_SERVER_ERROR

        logger.error(message, exc_info=exc_info)
        
        response_data = {'success': False, 'message': message}
        response = jsonify(response_data)
        response.status_code = int(status)
        return response
