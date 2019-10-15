# Looker Group Attribute Management: Dealer Group Consistency Cross-Instance

This project manages consistent deployment of Looker Groups, User Attributes,
and assignment of User Attributes to Groups across a Dev and Prod Looker instance. More
specifically, we expose a metadata table as a Look on the Dev instance. This metadata table
holds the true state of groups, attributes and mappings between them that should exist on
each instance to properly manage access controls and filters across groups. The metadata
table also allows for deployment of components to one or both dev and prod instances, and 
allows for specification of attribute type and default.

*Key*: The script automatically manages deployment of newly specified groups, user attributes,
and mappings of groups to attributes. It can do so across both instances, or to only one or the
other as specified in the table. It also can manage updates to attribute types or defaults, and
special cases like first and end of month attributes, which update once per month. As of now,
the script runs daily at midnight as configured via a Cloudwatch Rule. Note: The function does 
NOT manage mappings of these user attribute values to users, only to groups.

## Getting Started

This project runs very lean. Simply pull down the code and follow basic directions in the
Installing section to run, test and begin making edits to function code as needed.
You'll need to ensure that you have the necessary credentials to connect to both Dev and
Prod Looker instances. This can either be configured off a base user set to perform these
actions, or your User, assuming you have API and permissions to take actions like update
add or update user attributes and groups.

### Prerequisites

This function runs on Python 3.6 (and above). 
Package requirements specified in Requirements file, most notably is the lookerapi
package, which runs off Looker API version 3.0.0. Package should run on any 
operating system and standard dev environment. It may also be useful to have the AWS 
CLI configured on your machine, if you plan to deploy back to AWS Lambda locally.

### Installing

In order to run locally, you'll need config.yml file with mappings to each
of your Dev and Prod Looker instances. The file should be in the same directory
as the function. The file takes the following structure:

```
hosts:
 'devdealerware':
    host: '' # Looker instance URL
    token: '' # Your user API client ID
    secret: '' # Your user client secret
 'insights':
    host: '' # Looker instance URL
    token: '' # Your user API client ID
    secret: '' # Your user client secret
```

## Running the tests

Testing in the Lambda environment is simple - any event payload will trigger the process,
The testExecution event allows for manual function execution. As it is time-based, 
the function does not run dependent on event payload. NOTE: Future iterations could
implement further test cases, such as unit tests for Looker connectivity, adding or removing
groups and attributes, group-attribute mappings, etc.

## Deployment

Function structure is design to run on AWS Lambda, although it could be deployed
seamlessly to another major cloud platform (i.e. Azure or Google Cloud Functions) if
required. Integration of code will likely be employed in CI/CD pipeline. However,
to manually deploy, you can create a deployment package (Zip the code and its dependencies
in one folder) for Lambda and deploy to a designated S3 bucket or local path and run
`aws lambda update-function-code` AWS CLI command. You'll need to specify the function name,
location of the deployment package, and region.

## Built With

* [AWS Lambda](https://aws.amazon.com/lambda/) - Serverless compute.
* [Cloudwatch](https://aws.amazon.com/cloudwatch/) - Manages time-based event trigger.
* [Looker API](https://docs.looker.com/reference/api-and-integration/api-reference/v3.0) - 
Execution of updates to Looker objects.
* [Terraform](https://www.terraform.io/) - Infrastructure as code to deploy AWS cloud
infrastructural dependencies to deploy the function.

## Versioning

1.0.0 - Initial release. *(10/15/2019)*

## Authors

* **Johnathan Brooks** - *Initial work* - [4 Mile Analytics](https://4mile.io) 
