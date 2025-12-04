#!/usr/bin/env python3
"""Simple script to promote a user to admin."""

from auth import make_admin

# Replace 'username_here' with the actual username you want to make admin
username = input("Enter username to make admin: ")

try:
    make_admin(username)
    print(f"Successfully made '{username}' an admin!")
except Exception as e:
    print(f"Error: {e}")