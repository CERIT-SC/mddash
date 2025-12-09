import logging
from http import HTTPStatus

from flask import Response, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiResponse:
    """Standardized API response builder for success and error responses."""

    @staticmethod
    def success(data: object = None, status: HTTPStatus | int | None = None) -> Response:
        """
        Return a success response with the given data.

        Args:
            data: The data to return in the response.
            status: The HTTP status code (defaults to 200 OK).

        Returns:
            A Flask Response object containing the success response.
        """
        if status is None:
            status = HTTPStatus.OK

        response_data = {"success": True, "data": data}
        response = jsonify(response_data)
        response.status_code = int(status)
        return response

    @staticmethod
    def error(error: Exception | str, status: HTTPStatus | int | None = None) -> Response:
        """
        Return an error response with the given message. Also logs the error.

        Args:
            error: The error message or exception to return.
            status: The HTTP status code (defaults to 500 Internal Server Error).

        Returns:
            A Flask Response object containing the error response.
        """
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

        response_data = {"success": False, "message": message}
        response = jsonify(response_data)
        response.status_code = int(status)
        return response
