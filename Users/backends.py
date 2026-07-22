# backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        print(f"DEBUG: Attempting login for: {username}") # CHECK TERMINAL
        try:
            user = UserModel.objects.get(email=username)
            print(f"DEBUG: User found: {user.email}")
        except UserModel.DoesNotExist:
            print(f"DEBUG: User NOT found in DB")
            return None
        
        if user.check_password(password):
            print("DEBUG: Password is correct")
            if self.user_can_authenticate(user):
                print("DEBUG: Authentication SUCCESS")
                return user
            else:
                print("DEBUG: User failed user_can_authenticate (Check is_active/is_staff)")
                return None
        else:
            print("DEBUG: Password is INCORRECT")
            return None