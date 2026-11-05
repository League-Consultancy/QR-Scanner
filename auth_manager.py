#!/usr/bin/env python3
"""
LUXE-TRACE - Authentication & User Manager
Handles user storage, password hashing (scrypt/pbkdf2), and verification.
"""

import os
import json
import time
import re
from threading import Lock
from werkzeug.security import generate_password_hash, check_password_hash

DEFAULT_USERS_FILE = "users.json"

class AuthManager:
    def __init__(self, users_file=DEFAULT_USERS_FILE):
        self.users_file = users_file
        self.lock = Lock()
        self.users = {}
        self.init_users()

    def init_users(self):
        """Loads users from users.json, or creates default admin if not present."""
        with self.lock:
            if os.path.exists(self.users_file):
                try:
                    with open(self.users_file, "r", encoding="utf-8") as f:
                        self.users = json.load(f)
                        print(f"[Auth Manager] Loaded {len(self.users)} user account(s) from {self.users_file}")
                        return
                except Exception as e:
                    print(f"[Auth Manager] Warning: Error reading {self.users_file}: {e}")

            # If file doesn't exist or failed to load, initialize default admin
            default_user = os.environ.get("LUXE_ADMIN_USER", "admin")
            default_pass = os.environ.get("LUXE_ADMIN_PASS", "admin123")
            
            self.users = {
                default_user: {
                    "username": default_user,
                    "password_hash": generate_password_hash(default_pass),
                    "role": "admin",
                    "created_at": "initial"
                }
            }
            self._save_to_disk()
            print(f"[Auth Manager] Initialized default user '{default_user}' (password: {default_pass}) in {self.users_file}")

    def verify_user(self, username, password):
        """Verifies credentials against stored hashed passwords. Returns user dict or None."""
        if not username or not password:
            return None
        
        username = str(username).strip().lower()
        with self.lock:
            user = self.users.get(username)
            if not user:
                return None
            
            if check_password_hash(user.get("password_hash", ""), password):
                return {
                    "username": user.get("username", username),
                    "role": user.get("role", "admin")
                }
            return None

    def change_password(self, username, old_password, new_password):
        """Updates user password after verifying old password."""
        username = str(username).strip().lower()
        if not new_password or len(new_password) < 4:
            return {"status": "error", "message": "Password must be at least 4 characters."}

        with self.lock:
            user = self.users.get(username)
            if not user:
                return {"status": "error", "message": "User not found."}

            if not check_password_hash(user.get("password_hash", ""), old_password):
                return {"status": "error", "message": "Incorrect current password."}

            user["password_hash"] = generate_password_hash(new_password)
            self._save_to_disk()
            return {"status": "success", "message": "Password updated successfully."}

    def get_all_users(self):
        """Returns a list of all registered users without sensitive password hashes."""
        with self.lock:
            user_list = []
            for k, u in self.users.items():
                user_list.append({
                    "username": u.get("username", k),
                    "role": u.get("role", "operator"),
                    "created_at": u.get("created_at", "--")
                })
            # Sort: admins first, then alphabetical
            user_list.sort(key=lambda x: (x["role"] != "admin", x["username"]))
            return user_list

    def delete_user(self, username, current_username):
        """Deletes a user account. Prevents deleting oneself."""
        if not username:
            return {"status": "error", "message": "Username is required."}
        
        target = str(username).strip().lower()
        actor = str(current_username).strip().lower()

        if target == actor:
            return {"status": "error", "message": "You cannot delete your own active account."}

        with self.lock:
            if target not in self.users:
                return {"status": "error", "message": "User not found."}

            del self.users[target]
            self._save_to_disk()
            print(f"[Auth Manager] User '{target}' was deleted by '{actor}'.")
            return {"status": "success", "message": f"User '{username}' was successfully deleted."}

    def add_user(self, username, password, role="operator"):
        """
        Creates a new user account with hashed password.
        Validates username rules (min 3 chars, alphanumeric/underscore) and password length (min 6 chars).
        """
        if not username or not password:
            return {"status": "error", "message": "Username and password are required."}

        clean_user = str(username).strip()
        if len(clean_user) < 3:
            return {"status": "error", "message": "Username must be at least 3 characters."}

        if not re.match(r'^[a-zA-Z0-9_]+$', clean_user):
            return {"status": "error", "message": "Username can only contain letters, numbers, and underscores."}

        if len(password) < 6:
            return {"status": "error", "message": "Password must be at least 6 characters."}

        user_key = clean_user.lower()
        role_val = "admin" if str(role).strip().lower() == "admin" else "operator"

        with self.lock:
            if user_key in self.users:
                return {"status": "error", "message": f"Username '{clean_user}' is already taken."}

            new_user_record = {
                "username": clean_user,
                "password_hash": generate_password_hash(password),
                "role": role_val,
                "created_at": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            }
            self.users[user_key] = new_user_record
            self._save_to_disk()
            print(f"[Auth Manager] Successfully registered new user '{clean_user}' (role: {role_val}).")
            return {
                "status": "success",
                "message": f"Account '{clean_user}' created successfully.",
                "user": {
                    "username": clean_user,
                    "role": role_val
                }
            }

    def _save_to_disk(self):
        """Helper to write users dict to JSON file."""
        try:
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            print(f"[Auth Manager] Failed saving {self.users_file}: {e}")

