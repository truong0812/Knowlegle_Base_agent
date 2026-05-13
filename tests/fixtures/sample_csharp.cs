using System;
using System.Collections.Generic;

namespace MyApp.Services
{
    public class UserService
    {
        private readonly string _dbPath;

        public UserService(string dbPath)
        {
            _dbPath = dbPath;
        }

        public User CreateUser(string name, string email)
        {
            var user = new User(name, email);
            Save(user);
            return user;
        }

        public User? GetUser(string email)
        {
            return null;
        }

        private void Save(User user)
        {
        }
    }

    public class User
    {
        public string Name { get; set; }
        public string Email { get; set; }

        public User(string name, string email)
        {
            Name = name;
            Email = email;
        }
    }
}
