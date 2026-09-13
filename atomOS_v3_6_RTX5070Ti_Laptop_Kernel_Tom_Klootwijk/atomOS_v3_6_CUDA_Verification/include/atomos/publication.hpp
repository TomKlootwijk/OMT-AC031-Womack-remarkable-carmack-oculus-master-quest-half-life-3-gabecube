#pragma once
// Bounded publication retry for transient Windows filesystem sharing failures.
#include <chrono>
#include <filesystem>
#include <stdexcept>
#include <system_error>
#include <thread>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#elif defined(__linux__)
#include <cerrno>
#include <fcntl.h>
#include <sys/syscall.h>
#include <unistd.h>
#endif

namespace atomos { namespace publication {
namespace fs=std::filesystem;
inline bool transient(const std::error_code&error){
 if(error==std::errc::permission_denied||error==std::errc::device_or_resource_busy||error==std::errc::resource_unavailable_try_again)return true;
#if defined(_WIN32)
 if(error.category()==std::system_category())return error.value()==ERROR_ACCESS_DENIED||error.value()==ERROR_SHARING_VIOLATION||error.value()==ERROR_LOCK_VIOLATION;
#endif
 return false;
}
inline void require_absent(const fs::path&destination){
 std::error_code error;const auto status=fs::symlink_status(destination,error);
 if(error&&error!=std::errc::no_such_file_or_directory)throw fs::filesystem_error("inspect publication destination",destination,error);
 if(status.type()!=fs::file_type::not_found)throw fs::filesystem_error("publication destination already exists",destination,std::make_error_code(std::errc::file_exists));
}
inline void rename_no_replace(const fs::path&source,const fs::path&destination,std::error_code&error){
#if defined(_WIN32)
 // MoveFileW does not replace an existing destination, including a racing writer.
 if(::MoveFileW(source.c_str(),destination.c_str()))error.clear();else error=std::error_code(int(::GetLastError()),std::system_category());
#elif defined(__linux__) && defined(SYS_renameat2)
 // Linux RENAME_NOREPLACE=1; do not fall back to an overwriting rename.
 if(::syscall(SYS_renameat2,AT_FDCWD,source.c_str(),AT_FDCWD,destination.c_str(),1)==0)error.clear();else error=std::error_code(errno,std::generic_category());
#else
 (void)source;(void)destination;error=std::make_error_code(std::errc::operation_not_supported);
#endif
}
template<class Rename,class Sleep>
inline unsigned publish_directory(const fs::path&source,const fs::path&destination,Rename rename,Sleep sleep,unsigned attempts=21,std::chrono::milliseconds delay=std::chrono::milliseconds(50)){
 if(!attempts||delay.count()<0)throw std::invalid_argument("invalid bounded publication retry policy");
 for(unsigned attempt=0;attempt<attempts;++attempt){
  require_absent(destination);std::error_code error;rename(source,destination,error);if(!error)return attempt+1;
  if(!transient(error)||attempt+1==attempts)throw fs::filesystem_error("publish verified directory",source,destination,error);
  sleep(delay);
 }
 throw std::logic_error("unreachable publication retry result");
}
inline unsigned publish_directory(const fs::path&source,const fs::path&destination){
 return publish_directory(source,destination,rename_no_replace,[](std::chrono::milliseconds delay){std::this_thread::sleep_for(delay);});
}
}} // atomos::publication
