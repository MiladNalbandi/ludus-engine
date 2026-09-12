// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence;

import io.ludus.application.content.port.out.UnitOfWork;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * One transaction, via Spring.
 *
 * <p>{@link TransactionTemplate} rather than {@code @Transactional}, because the caller is an
 * application-layer object that Spring does not proxy — the annotation would be silently ignored
 * there, which is the worst of the available failures: a batch that appears atomic and is not.
 */
@Component
public class SpringUnitOfWork implements UnitOfWork {

    private final TransactionTemplate transactions;

    SpringUnitOfWork(PlatformTransactionManager transactionManager) {
        this.transactions = new TransactionTemplate(transactionManager);
    }

    @Override
    public <T> T inOne(Supplier<T> work) {
        return transactions.execute(status -> work.get());
    }
}
