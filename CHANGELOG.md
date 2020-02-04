# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2020-02-04
### Added
- SQLite database for handling the data related to comics
- SQLite convenience methods in helper
- Makefile options, such as, debug and git-dirty-check

### Changed
- All comics at hs.fi now available for comic operations instead of only Fok_It
- All dependencies have been updated to latest
- Container Python version updated from 3.7.5 to 3.8.1

### Fixed
- Signals are handled correctly in the container so SIGTERM will be passed properly

## [0.2.2] - 2020-01-03
### Fixed
- Date checking in daily comic postings was incorrect

## [0.2.1] - 2019-12-27
### Fixed
- Prevent daily Fok-It comics being posted on incorrect day if there are no updates

## [0.2.0] - 2019-12-25
### Added
- Changelog documentation
- Fok-It comic strip posting capabilities
- Timezone (Europe/Helsinki) configuration within Docker image
- JSON based configuration file
- More Makefile targets
- Separate docker-compose-release.yml file for running release versions
