#include <string>
#include <vector>
#include <optional>

namespace myapp {
namespace services {

class User {
public:
    std::string name;
    std::string email;

    User(std::string name, std::string email)
        : name(std::move(name)), email(std::move(email)) {}
};

class UserService {
public:
    UserService(const std::string& db_path);

    User create_user(const std::string& name, const std::string& email) {
        User user(name, email);
        save(user);
        return user;
    }

    std::optional<User> get_user(const std::string& email) {
        return std::nullopt;
    }

private:
    std::string db_path_;
    void save(const User& user) {}
};

bool validate_email(const std::string& email) {
    return email.find('@') != std::string::npos;
}

} // namespace services
} // namespace myapp
