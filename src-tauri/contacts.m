// The contacts of the Mac or the iPhone, for the contact picker and the names of the numbers in the lists.
// One file for both: the Contacts framework is the same there. lib.rs frees the string that this returns.
#import <Contacts/Contacts.h>
#include <string.h>

char *lines_contacts(void) {
    @autoreleasepool {
        CNContactStore *store = [CNContactStore new];
        // The first call asks for access, and waits for the answer of the user.
        if ([CNContactStore authorizationStatusForEntityType:CNEntityTypeContacts] == CNAuthorizationStatusNotDetermined) {
            dispatch_semaphore_t answered = dispatch_semaphore_create(0);
            [store requestAccessForEntityType:CNEntityTypeContacts completionHandler:^(BOOL granted, NSError *error) {
                dispatch_semaphore_signal(answered);
            }];
            dispatch_semaphore_wait(answered, dispatch_time(DISPATCH_TIME_NOW, 300 * NSEC_PER_SEC));
        }
        NSArray *keys = @[[CNContactFormatter descriptorForRequiredKeysForStyle:CNContactFormatterStyleFullName],
                          CNContactPhoneNumbersKey, CNContactOrganizationNameKey];
        CNContactFetchRequest *request = [[CNContactFetchRequest alloc] initWithKeysToFetch:keys];
        request.sortOrder = CNContactSortOrderUserDefault;
        NSMutableArray *rows = [NSMutableArray array];
        // With no access, the fetch fails and the list stays empty.
        [store enumerateContactsWithFetchRequest:request error:nil usingBlock:^(CNContact *contact, BOOL *stop) {
            NSString *name = [CNContactFormatter stringFromContact:contact style:CNContactFormatterStyleFullName];
            if (name.length == 0) name = contact.organizationName;
            for (CNLabeledValue<CNPhoneNumber *> *phone in contact.phoneNumbers) {
                NSString *label = phone.label ? [CNLabeledValue localizedStringForLabel:phone.label] : @"";
                [rows addObject:@{@"name": name ?: @"", @"number": phone.value.stringValue ?: @"", @"label": label ?: @""}];
            }
        }];
        NSData *json = [NSJSONSerialization dataWithJSONObject:rows options:0 error:nil];
        NSString *text = json ? [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] : @"[]";
        return strdup(text.UTF8String);
    }
}
