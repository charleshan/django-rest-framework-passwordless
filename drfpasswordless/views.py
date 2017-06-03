import logging
from rest_framework import parsers, renderers, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .settings import api_settings
from .serializers import (EmailAuthSerializer,
                          MobileAuthSerializer,
                          CallbackTokenAuthSerializer,
                          CallbackTokenVerificationSerializer,
                          EmailVerificationSerializer,
                          MobileVerificationSerializer,)
from .utils import send_sms_with_callback_token, send_email_with_callback_token, create_callback_token_for_user

log = logging.getLogger(__name__)


class AbstractBaseObtainCallbackToken(APIView):
    """
    This returns a 6-digit callback token we can trade for a user's Auth Token.
    """
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)

    success_response = "A login token has been sent to you."
    failure_response = "Unable to send you a login code. Try again later."

    message_payload = {}

    @property
    def serializer_class(self):
        # Our serializer depending on type
        raise NotImplementedError

    @property
    def alias_type(self):
        # Alias Type
        raise NotImplementedError

    @property
    def send_action(self):
        # Our send function depending on type
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        if self.alias_type.upper() not in api_settings.PASSWORDLESS_AUTH_TYPES:
            # Only allow auth types allowed in settings.
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(data=request.data, context={'request': request})
        if serializer.is_valid(raise_exception=True):
            # Validate -
            user = serializer.validated_data['user']
            # Create callback token for sending alias type
            token = create_callback_token_for_user(user, self.alias_type)
            # Send to alias
            success = self.send_action(user, token, **self.message_payload)

            # Respond With Success Or Failure of Sent
            if success:
                status_code = status.HTTP_200_OK
                response_detail = self.success_response
            else:
                status_code = status.HTTP_400_BAD_REQUEST
                response_detail = self.failure_response
            return Response({'detail': response_detail}, status=status_code)
        else:
            return Response(serializer.error_messages, status=status.HTTP_400_BAD_REQUEST)


class ObtainEmailCallbackToken(AbstractBaseObtainCallbackToken):
    serializer_class = EmailAuthSerializer
    send_action = send_email_with_callback_token
    success_response = "A login token has been sent to your email."
    failure_response = "Unable to email you a login code. Try again later."

    alias_type = 'email'

    email_subject = api_settings.PASSWORDLESS_EMAIL_SUBJECT
    email_plaintext = api_settings.PASSWORDLESS_EMAIL_PLAINTEXT_MESSAGE
    email_html = api_settings.PASSWORDLESS_EMAIL_TOKEN_HTML_TEMPLATE_NAME
    message_payload = {'email_subject': email_subject,
                       'email_plaintext': email_plaintext,
                       'email_html': email_html}


class ObtainMobileCallbackToken(AbstractBaseObtainCallbackToken):
    serializer_class = MobileAuthSerializer
    send_action = send_sms_with_callback_token
    success_response = "We texted you a login code."
    failure_response = "Unable to send you a login code. Try again later."

    alias_type = 'mobile'

    mobile_message = api_settings.PASSWORDLESS_MOBILE_MESSAGE
    message_payload = {'mobile_message': mobile_message}


class ObtainEmailVerificationCallbackToken(AbstractBaseObtainCallbackToken):
    permission_classes = (IsAuthenticated,)
    serializer_class = EmailVerificationSerializer
    send_action = send_email_with_callback_token
    success_response = "A verification token has been sent to your email."
    failure_response = "Unable to email you a verification code. Try again later."

    alias_type = 'email'

    email_subject = api_settings.PASSWORDLESS_EMAIL_VERIFICATION_SUBJECT
    email_plaintext = api_settings.PASSWORDLESS_EMAIL_VERIFICATION_PLAINTEXT_MESSAGE
    email_html = api_settings.PASSWORDLESS_EMAIL_VERIFICATION_TOKEN_HTML_TEMPLATE_NAME
    message_payload = {'email_subject': email_subject,
                       'email_plaintext': email_plaintext,
                       'email_html': email_html}


class ObtainMobileVerificationCallbackToken(AbstractBaseObtainCallbackToken):
    permission_classes = (IsAuthenticated,)
    serializer_class = MobileVerificationSerializer
    send_action = send_sms_with_callback_token
    success_response = "We texted you a verification code."
    failure_response = "Unable to send you a verification code. Try again later."

    alias_type = 'mobile'

    mobile_message = api_settings.PASSWORDLESS_MOBILE_MESSAGE
    message_payload = {'mobile_message': mobile_message}


class AbstractBaseObtainAuthToken(APIView):
    """
    This is a duplicate of rest_framework's own ObtainAuthToken method.
    Instead, this returns an Auth Token based on our 6 digit callback token and source.
    """
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = None

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid(raise_exception=True):
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)

            if created:
                # Initially set an unusable password if a user is created through this.
                user.set_unusable_password()
                user.save()

            if token:
                # Return our key for consumption.
                return Response({'token': token.key}, status=status.HTTP_200_OK)
        else:
            log.error(
                "Couldn't log in unknown user. Errors on serializer: %s" % (serializer.error_messages, ))
        return Response({'detail': 'Couldn\'t log you in. Try again later.'},
                        status=status.HTTP_400_BAD_REQUEST)


class ObtainAuthTokenFromCallbackToken(AbstractBaseObtainAuthToken):
    """
    This is a duplicate of rest_framework's own ObtainAuthToken method.
    Instead, this returns an Auth Token based on our callback token and source.
    """
    serializer_class = CallbackTokenAuthSerializer


class VerifyAliasFromCallbackToken(APIView):
    """
    This verifies an alias on correct callback token entry using the same logic as auth.
    Should be refactored at some point.
    """
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = CallbackTokenVerificationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'user_id': self.request.user.id})
        if serializer.is_valid(raise_exception=True):

            return Response({'detail': 'Alias verified.'}, status=status.HTTP_200_OK)
        else:
            log.error(
                "Couldn't verify unknown user. Errors on serializer: %s" % (serializer.error_messages, ))

        return Response({'detail': 'We couldn\'t verify this alias. Try again later.'}, status.HTTP_400_BAD_REQUEST)
